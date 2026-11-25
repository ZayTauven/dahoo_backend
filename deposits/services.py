"""
Caution : ce que l'agence détient, et le décompte à la sortie.

- Les loyers impayés retenus deviennent un vrai paiement (« Retenue sur caution ») affecté aux échéances :
  quittances, retards et relevé du bailleur restent justes. L'argent étant déjà entré avec la caution, ce
  paiement ne compte pas une seconde fois dans l'argent encaissé (PaymentQuerySet.cash).
- Les autres retenues (réparations, factures) reviennent au bailleur, sans commission : elles compensent les
  dépenses qu'il supporte.
- On ne retient jamais plus que la caution : le surplus reste dû par le locataire.
"""

from datetime import datetime, time
from decimal import Decimal

from django.db import transaction
from django.db.models import Prefetch, Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from deposits.models import DepositDeduction, DepositSettlement
from inspections.services import faults
from leases.models import LeaseContract
from leases.tenants import tenant_names
from payments.models import DEPOSIT_METHOD, Payment, PaymentMethod, PaymentSchedule
from payments.services import allocate_payment, allocated_total, cancel_payment, due_schedules, refresh_paid

ZERO = Decimal("0")
ENDED = ("TERMINATED", "COMPLETED")

DEPOSIT_STATES = [
    ("NONE", "Aucune caution"),
    ("EXPECTED", "À encaisser"),
    ("HELD", "Détenue"),
    ("TO_RETURN", "À rendre"),
    ("SETTLED", "Réglée"),
]


def deposit_schedule(lease):
    return lease.schedules.filter(schedule_type="DEPOSIT").order_by("id").first()


def held_amount(lease):
    """
    (montant détenu, déclaré). Avec une échéance de caution, ce qui a été encaissé ; sans (bail repris dans
    Dahoo), la caution inscrite au bail, à confirmer au moment du décompte.
    """
    schedule = deposit_schedule(lease)
    if schedule:
        return allocated_total(schedule.allocations.all()), False
    if lease.deposit_unpaid:
        return ZERO, False
    return lease.deposit_amount, True


def unpaid_schedules(lease):
    """Loyers et charges encore dus, les plus anciens d'abord (la caution elle-même n'en fait pas partie)."""
    rows = []
    for schedule in due_schedules(lease).exclude(schedule_type="DEPOSIT"):
        remaining = schedule.amount_due - allocated_total(schedule.allocations.all())
        if remaining > 0:
            rows.append((schedule, remaining))
    return rows


def deposit_state(lease, held, declared, settlement):
    if settlement:
        return "SETTLED"
    if lease.status in ENDED:
        return "TO_RETURN" if held > 0 else "NONE"
    if lease.status != "ACTIVE" or lease.deposit_amount <= 0:
        return "HELD" if held > 0 and lease.status == "ACTIVE" else "NONE"
    return "HELD" if held > 0 else "EXPECTED"


def deposit_summary(lease):
    held, declared = held_amount(lease)
    settlement = lease.deposit_settlements.valid().select_related("method").prefetch_related("deductions").first()
    unpaid = unpaid_schedules(lease)
    return {
        "lease": lease.pk,
        "state": deposit_state(lease, held, declared, settlement),
        "held": held,
        "declared": declared,
        "unpaid": sum((remaining for _, remaining in unpaid), ZERO),
        "unpaid_count": len(unpaid),
        "faults": [{"room": item.room, "label": item.label, "condition": item.condition, "note": item.note} for item in faults(lease)],
        "exit_inspection": lease.inspections.filter(kind="EXIT").values_list("status", flat=True).first() or "",
        "settlement": settlement,
    }


def build_deposits(organization):
    """Cautions de l'agence : détenues, à rendre, rendues. La plus pressée d'abord."""
    order = {code: index for index, code in enumerate(("TO_RETURN", "EXPECTED", "HELD", "SETTLED"))}
    name = tenant_names(organization)
    leases = (
        LeaseContract.objects.filter(organization=organization)
        .filter(Q(status="ACTIVE") | Q(status__in=ENDED))
        .filter(Q(deposit_amount__gt=0) | Q(schedules__schedule_type="DEPOSIT"))
        .distinct().select_related("tenant", "unit__building__property")
        .prefetch_related(
            Prefetch("schedules", PaymentSchedule.objects.filter(schedule_type="DEPOSIT").prefetch_related("allocations").order_by("id"), to_attr="deposit_rows"),
            Prefetch("deposit_settlements", DepositSettlement.objects.valid(), to_attr="valid_settlements"),
        )
    )
    rows = []
    for lease in leases:
        if lease.deposit_rows:
            held, declared = sum((a.allocated_amount for a in lease.deposit_rows[0].allocations.all()), ZERO), False
        else:
            held, declared = (ZERO, False) if lease.deposit_unpaid else (lease.deposit_amount, True)
        settlement = next(iter(lease.valid_settlements), None)
        state = deposit_state(lease, held, declared, settlement)
        if state == "NONE":
            continue
        rows.append({
            "lease": lease.pk, "state": state, "tenant_name": name(lease.tenant), "unit_reference": lease.unit.reference,
            "property_name": lease.unit.building.property.name, "held": settlement.held_amount if settlement else held,
            "declared": declared, "ended_on": lease.ended_on, "refunded": settlement.refund_amount if settlement else None,
            "settled_on": settlement.settled_on if settlement else None, "expected": lease.deposit_amount,
        })
    rows.sort(key=lambda row: (order[row["state"]], row["ended_on"] or timezone.localdate(), row["property_name"], row["unit_reference"]))

    def total(*states):
        return sum((row["held"] for row in rows if row["state"] in states), ZERO)

    return {
        "held": total("HELD", "TO_RETURN"),
        "to_return": total("TO_RETURN"),
        "to_return_count": sum(row["state"] == "TO_RETURN" for row in rows),
        "held_count": sum(row["state"] in ("HELD", "TO_RETURN") for row in rows),
        "rows": rows,
    }


def deposits_to_return(organization):
    """Baux terminés dont la caution attend (point du jour)."""
    return [row for row in build_deposits(organization)["rows"] if row["state"] == "TO_RETURN"]


@transaction.atomic
def settle_deposit(lease, *, user, retain_unpaid=ZERO, deductions=(), held=None, method=None, reference="", note="", settled_on=None):
    lease = LeaseContract.objects.select_for_update().get(pk=lease.pk)
    today = timezone.localdate()
    settled_on = settled_on or today
    if lease.status not in ENDED:
        raise ValidationError({"detail": "La caution se règle une fois le bail résilié ou clôturé."})
    if lease.deposit_settlements.valid().exists():
        raise ValidationError({"detail": "La caution de ce bail est déjà réglée."})
    if settled_on > today:
        raise ValidationError({"settled_on": "La date ne peut pas être à venir."})

    actual, declared = held_amount(lease)
    if declared:
        # Aucun encaissement dans Dahoo : l'agence confirme ce qu'elle a réellement reçu.
        held = actual if held is None else held
    else:
        if held is not None and held != actual:
            raise ValidationError({"held": "Le montant détenu vient de l'encaissement de la caution : il ne se modifie pas ici."})
        held = actual
    # Caution inscrite au bail mais jamais reçue : un décompte à zéro la sort des cautions à rendre.
    if held <= 0 and not (declared and actual > 0):
        raise ValidationError({"detail": "Aucune caution n'a été versée pour ce bail."})

    unpaid = unpaid_schedules(lease)
    due = sum((remaining for _, remaining in unpaid), ZERO)
    if retain_unpaid < 0 or retain_unpaid > due:
        raise ValidationError({"retain_unpaid": "Vous ne pouvez pas retenir plus que les loyers encore dus."})
    retained = retain_unpaid + sum((deduction["amount"] for deduction in deductions), ZERO)
    if retained > held:
        raise ValidationError({"deductions": "Les retenues dépassent la caution : le surplus reste dû par le locataire."})
    refund = held - retained
    if refund > 0 and method is None:
        raise ValidationError({"method": "Indiquez comment la caution est rendue."})

    payment = None
    if retain_unpaid > 0:
        payment = Payment.objects.create(
            organization_id=lease.organization_id, payer_id=lease.tenant_id, recorded_by=user, amount_paid=retain_unpaid,
            payment_method=PaymentMethod.objects.get_or_create(code=DEPOSIT_METHOD, defaults={"label": "Retenue sur caution"})[0],
            payment_date=timezone.now() if settled_on == today else timezone.make_aware(datetime.combine(settled_on, time(12))),
            note=f"Loyers soldés par la caution, bail n°{lease.pk}",
        )
        left, allocations = retain_unpaid, []
        for schedule, remaining in unpaid:
            share = min(left, remaining)
            if share <= 0:
                break
            allocations.append({"schedule": schedule, "amount": share})
            left -= share
        allocate_payment(payment, allocations)

    # Caution versée en partie : plus rien n'est attendu du locataire à ce titre.
    schedule, due_before = deposit_schedule(lease), None
    if schedule and not schedule.is_paid:
        due_before, schedule.amount_due = schedule.amount_due, held
        schedule.save(update_fields=["amount_due"])
        refresh_paid(schedule)

    settlement = DepositSettlement.objects.create(
        organization_id=lease.organization_id, lease=lease, held_amount=held, refund_amount=refund, settled_on=settled_on,
        method=method if refund > 0 else None, reference=reference.strip() if refund > 0 else "", note=note.strip(),
        rent_payment=payment, deposit_due_before=due_before, recorded_by=user,
    )
    DepositDeduction.objects.bulk_create(DepositDeduction(settlement=settlement, **deduction) for deduction in deductions)
    return settlement


@transaction.atomic
def cancel_settlement(settlement, *, user, reason):
    settlement = DepositSettlement.objects.select_for_update().get(pk=settlement.pk)
    if settlement.cancelled_at:
        raise ValidationError({"detail": "Ce décompte est déjà annulé."})
    if settlement.rent_payment_id:
        cancel_payment(settlement.rent_payment, user=user, reason=reason, from_settlement=True)
    if settlement.deposit_due_before is not None:
        schedule = deposit_schedule(settlement.lease)
        schedule.amount_due = settlement.deposit_due_before
        schedule.save(update_fields=["amount_due"])
        refresh_paid(schedule)
    settlement.cancelled_at, settlement.cancelled_by, settlement.cancel_reason = timezone.now(), user, reason
    settlement.save(update_fields=["cancelled_at", "cancelled_by", "cancel_reason"])
    return settlement

