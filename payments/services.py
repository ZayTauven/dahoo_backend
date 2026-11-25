from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from payments.models import DEPOSIT_METHOD, Payment, PaymentAllocation, PaymentSchedule

ZERO = Decimal("0")


def allocated_total(queryset):
    return queryset.aggregate(total=Sum("allocated_amount"))["total"] or ZERO


def schedule_party_id(schedule):
    """Compte qui doit l'échéance : le locataire du bail ou l'acquéreur de la vente."""
    if schedule.lease_contract_id:
        return schedule.lease_contract.tenant_id
    return schedule.sale_contract.buyer_id


def refresh_paid(schedule):
    """Recalcule `is_paid` d'après les affectations (à appeler après tout changement de montant)."""
    schedule.is_paid = allocated_total(schedule.allocations.all()) >= schedule.amount_due
    schedule.save(update_fields=["is_paid"])
    return schedule


def commission_rate(schedule):
    """Taux de commission de l'agence au jour de l'encaissement (0 hors loyers), figé sur l'affectation."""
    if schedule.schedule_type not in ("RENT", "ARREARS") or not schedule.lease_contract_id:
        return ZERO
    return schedule.lease_contract.unit.building.property.commission_rate


@transaction.atomic
def allocate_payment(payment, allocations):
    """
    Répartit un paiement sur des échéances.
    `allocations` : liste de {"schedule": PaymentSchedule, "amount": Decimal}.
    Refuse l'échéance d'un autre locataire, un paiement annulé, et de dépasser le montant du paiement
    ou le reste dû d'une échéance ; puis recalcule `is_paid` sur chaque échéance touchée.
    """
    if not allocations:
        return []
    # Verrouille le paiement : son montant disponible ne doit pas changer pendant le calcul.
    payment = Payment.objects.select_for_update().get(pk=payment.pk)
    if payment.cancelled_at:
        raise ValidationError({"allocations": "Ce paiement est annulé."})

    schedule_ids = [a["schedule"].pk for a in allocations]
    if len(schedule_ids) != len(set(schedule_ids)):
        raise ValidationError({"allocations": "Une même échéance apparaît plusieurs fois."})

    # Verrouille les échéances pour éviter une double affectation concurrente.
    schedules = {
        s.pk: s
        for s in PaymentSchedule.objects.select_for_update(of=("self",))
        .select_related("lease_contract__unit__building__property", "sale_contract")
        .filter(pk__in=schedule_ids)
    }
    if any(schedule_party_id(s) != payment.payer_id for s in schedules.values()):
        raise ValidationError({"allocations": "Une échéance ne peut être réglée que par le locataire qui la doit."})

    requested = sum((a["amount"] for a in allocations), ZERO)
    available = payment.amount_paid - allocated_total(payment.allocations.all())
    if requested > available:
        raise ValidationError(
            {"allocations": f"Montant affecté ({requested}) supérieur au montant disponible du paiement ({available})."}
        )

    created = []
    for allocation in allocations:
        schedule = schedules[allocation["schedule"].pk]
        remaining = schedule.amount_due - allocated_total(schedule.allocations.all())
        if allocation["amount"] > remaining:
            raise ValidationError(
                {"allocations": f"L'échéance {schedule.pk} n'a plus que {remaining} à régler."}
            )
        created.append(
            PaymentAllocation.objects.create(
                payment=payment,
                schedule=schedule,
                allocated_amount=allocation["amount"],
                commission_rate=commission_rate(schedule),
            )
        )
        refresh_paid(schedule)
    return created


def due_schedules(lease):
    """Échéances non soldées d'un bail, les plus anciennes d'abord."""
    return lease.schedules.filter(is_paid=False).order_by("due_date", "id")


@transaction.atomic
def collect_rent(lease, *, recorded_by, amount, payment_method, **fields):
    """
    Encaissement rapide : enregistre le paiement du locataire et solde ses échéances de ce bail, les
    plus anciennes d'abord. Ce qui dépasse reste disponible sur le paiement (avance).
    """
    payment = Payment.objects.create(
        organization_id=lease.organization_id,
        payer_id=lease.tenant_id,
        recorded_by=recorded_by,
        amount_paid=amount,
        payment_method=payment_method,
        **fields,
    )
    left, allocations = amount, []
    for schedule in due_schedules(lease).select_for_update():
        remaining = schedule.amount_due - allocated_total(schedule.allocations.all())
        share = min(left, remaining)
        if share <= ZERO:
            continue
        allocations.append({"schedule": schedule, "amount": share})
        left -= share
        if left <= ZERO:
            break
    allocate_payment(payment, allocations)
    email_documents(payment)
    return payment


def email_documents(payment):
    """Quittance ou reçu par e-mail après la transaction, si l'agence l'a choisi. Jamais bloquant."""
    if not payment.organization.email_receipts:
        return
    from mailing.agency import email_payment_documents
    from notifications.signals import after_commit

    after_commit(lambda: email_payment_documents(payment, strict=False, dedupe_key=""))


@transaction.atomic
def cancel_payment(payment, *, user, reason, from_settlement=False):
    """
    Annule un paiement saisi par erreur : il reste visible avec son motif, mais ses affectations sont
    retirées et les échéances redeviennent dues.
    """
    payment = Payment.objects.select_for_update().get(pk=payment.pk)
    if payment.cancelled_at:
        raise ValidationError({"detail": "Ce paiement est déjà annulé."})
    if payment.payment_method.code == DEPOSIT_METHOD and not from_settlement:
        raise ValidationError({"detail": "Cette retenue vient d'un décompte de caution : annulez le décompte sur la fiche du bail."})
    schedules = list(
        PaymentSchedule.objects.select_for_update(of=("self",)).filter(
            pk__in=payment.allocations.values("schedule_id")
        )
    )
    payment.allocations.all().delete()
    for schedule in schedules:
        refresh_paid(schedule)
    payment.cancelled_at = timezone.now()
    payment.cancelled_by = user
    payment.cancel_reason = reason
    payment.save(update_fields=["cancelled_at", "cancelled_by", "cancel_reason"])
    return payment
