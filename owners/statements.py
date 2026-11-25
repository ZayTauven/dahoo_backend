"""
Relevé de gestion d'un bailleur : loyers encaissés, commission de l'agence, dépenses, reversements et
solde à reverser. Tout est recalculé à partir des écritures ; seul le taux de commission est figé, sur
chaque encaissement (PaymentAllocation.commission_rate).

La caution n'entre pas dans le solde : elle est détenue pour le compte du locataire. À la sortie, ce qui en est
retenu pour réparations ou factures lui revient (sans commission), les loyers retenus étant des encaissements.
"""

from collections import defaultdict
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Sum
from django.utils import timezone

from analytics.dashboard import add_months, schedules_with_remaining
from deposits.models import DepositDeduction
from leases.tenants import tenant_names
from owners.models import Expense, OwnerPayout
from payments.models import PaymentAllocation

ZERO = Decimal("0")
# Échéances dont l'encaissement revient au bailleur.
OWNER_TYPES = ("RENT", "CHARGE", "ARREARS")
OWNER = "schedule__lease_contract__unit__building__property__owner"


def commission(amount, rate):
    return (amount * rate / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _collections(organization, **filters):
    """Encaissements de loyers et de charges, paiements annulés exclus (leurs affectations sont retirées)."""
    return PaymentAllocation.objects.filter(
        schedule__organization=organization, schedule__schedule_type__in=OWNER_TYPES, **filters
    )


DEDUCTION_OWNER = "settlement__lease__unit__building__property__owner"


def _retentions(organization, **filters):
    return DepositDeduction.objects.filter(settlement__organization=organization, settlement__cancelled_at__isnull=True, **filters)


def owner_balances(organization, *, until=None, owner=None):
    """
    Solde à reverser par bailleur : {id: {"collected", "commission", "retentions", "expenses", "payouts", "balance"}},
    sur toutes les écritures antérieures à `until` (exclu). En quelques requêtes, pour les listes.
    """
    totals = defaultdict(lambda: {"collected": ZERO, "commission": ZERO, "retentions": ZERO, "expenses": ZERO, "payouts": ZERO})
    only = {OWNER: owner} if owner else {f"{OWNER}__isnull": False}
    before = {"payment__payment_date__date__lt": until} if until else {}
    rows = _collections(organization, **only, **before).values_list(OWNER, "allocated_amount", "commission_rate")
    for owner_id, amount, rate in rows:
        totals[owner_id]["collected"] += amount
        totals[owner_id]["commission"] += commission(amount, rate)

    expenses = Expense.objects.filter(organization=organization, property__owner__isnull=False)
    payouts = OwnerPayout.objects.filter(organization=organization, cancelled_at__isnull=True)
    retentions = _retentions(organization, **({DEDUCTION_OWNER: owner} if owner else {f"{DEDUCTION_OWNER}__isnull": False}))
    if until:
        retentions = retentions.filter(settlement__settled_on__lt=until)
    for owner_id, total in retentions.order_by().values_list(DEDUCTION_OWNER).annotate(total=Sum("amount")):
        totals[owner_id]["retentions"] += total
    if owner:
        expenses, payouts = expenses.filter(property__owner=owner), payouts.filter(owner=owner)
    if until:
        expenses, payouts = expenses.filter(spent_on__lt=until), payouts.filter(paid_on__lt=until)
    for owner_id, total in expenses.order_by().values_list("property__owner").annotate(total=Sum("amount")):
        totals[owner_id]["expenses"] += total
    for owner_id, total in payouts.order_by().values_list("owner").annotate(total=Sum("amount")):
        totals[owner_id]["payouts"] += total

    for row in totals.values():
        row["balance"] = row["collected"] - row["commission"] + row["retentions"] - row["expenses"] - row["payouts"]
    return totals


def build_statement(owner, *, month):
    """Relevé d'un mois calendaire."""
    organization = owner.organization
    starts = month.replace(day=1)
    ends = add_months(starts, 1)
    name = tenant_names(organization)

    units = {}

    def unit_row(lease):
        unit = lease.unit
        return units.setdefault(lease.pk, {
            "lease": lease.pk,
            "unit_reference": unit.reference,
            "property_name": unit.building.property.name,
            "tenant_name": name(lease.tenant),
            "expected": ZERO, "collected": ZERO, "commission": ZERO, "unpaid": ZERO,
        })

    lease_path = ("schedule__lease_contract__tenant", "schedule__lease_contract__unit__building__property")
    collected = (
        _collections(organization, **{OWNER: owner}, payment__payment_date__date__gte=starts, payment__payment_date__date__lt=ends)
        .select_related(*lease_path)
    )
    for allocation in collected:
        row = unit_row(allocation.schedule.lease_contract)
        row["collected"] += allocation.allocated_amount
        row["commission"] += commission(allocation.allocated_amount, allocation.commission_rate)

    # Appelé dans le mois, et impayé à la fin du mois (toutes échéances passées).
    schedules = (
        schedules_with_remaining(organization)
        .filter(
            lease_contract__unit__building__property__owner=owner,
            schedule_type__in=OWNER_TYPES,
            due_date__lt=ends,
        )
        .select_related("lease_contract__tenant", "lease_contract__unit__building__property")
    )
    today = timezone.localdate()
    for schedule in schedules.exclude(due_date__lt=starts, is_paid=True):
        row = unit_row(schedule.lease_contract)
        if schedule.due_date >= starts:
            row["expected"] += schedule.amount_due
        if schedule.due_date <= today:
            row["unpaid"] += schedule.remaining

    rows = sorted(units.values(), key=lambda row: (row["property_name"], row["unit_reference"], row["lease"]))
    expenses = list(
        Expense.objects.filter(organization=organization, property__owner=owner, spent_on__gte=starts, spent_on__lt=ends)
        .select_related("property", "unit").order_by("spent_on", "id")
    )
    payouts = list(
        OwnerPayout.objects.filter(owner=owner, cancelled_at__isnull=True, paid_on__gte=starts, paid_on__lt=ends)
        .order_by("paid_on", "id")
    )
    retentions = list(
        _retentions(organization, **{DEDUCTION_OWNER: owner}, settlement__settled_on__gte=starts, settlement__settled_on__lt=ends)
        .select_related("settlement__lease__unit__building__property").order_by("settlement__settled_on", "id")
    )
    previous = owner_balances(organization, until=starts, owner=owner).get(owner.pk)
    opening = previous["balance"] if previous else ZERO
    totals = {
        "expected": sum((row["expected"] for row in rows), ZERO),
        "collected": sum((row["collected"] for row in rows), ZERO),
        "commission": sum((row["commission"] for row in rows), ZERO),
        "unpaid": sum((row["unpaid"] for row in rows), ZERO),
        "retentions": sum((retention.amount for retention in retentions), ZERO),
        "expenses": sum((expense.amount for expense in expenses), ZERO),
        "payouts": sum((payout.amount for payout in payouts), ZERO),
    }
    net = totals["collected"] - totals["commission"] + totals["retentions"] - totals["expenses"]
    return {
        "owner": owner.pk,
        "owner_name": owner.full_name,
        "month": starts,
        "ends": ends - timedelta(days=1),
        "opening_balance": opening,
        **totals,
        "net": net,
        "closing_balance": opening + net - totals["payouts"],
        "units": rows,
        "retention_lines": [
            {
                "id": retention.pk,
                "date": retention.settlement.settled_on,
                "label": f"{retention.get_kind_display()} : {retention.label}",
                "property_name": retention.settlement.lease.unit.building.property.name,
                "unit_reference": retention.settlement.lease.unit.reference,
                "amount": retention.amount,
            }
            for retention in retentions
        ],
        "expense_lines": [
            {
                "id": expense.pk,
                "date": expense.spent_on,
                "label": expense.label,
                "property_name": expense.property.name,
                "unit_reference": expense.unit.reference if expense.unit else "",
                "amount": expense.amount,
            }
            for expense in expenses
        ],
        "payout_lines": [
            {
                "id": payout.pk,
                "date": payout.paid_on,
                "channel": payout.get_channel_display(),
                "reference": payout.reference,
                "amount": payout.amount,
            }
            for payout in payouts
        ],
    }
