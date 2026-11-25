"""
Loyers du mois : une ligne par bail, avec ce qui est dû, réglé et en retard. C'est l'écran de travail
quotidien de l'agence : encaisser, relancer, envoyer la quittance.
"""

from collections import defaultdict
from decimal import Decimal

from django.db.models import Max, Q
from django.utils import timezone

from analytics.dashboard import add_months, schedules_with_remaining
from leases.models import LeaseContract, Tenant
from leases.tenants import tenant_names
from mailing.addresses import is_deliverable

ZERO = Decimal("0")

RENT_STATUSES = [
    ("PAID", "Réglé"),
    ("PARTIAL", "Partiel"),
    ("LATE", "En retard"),
    ("DUE", "À venir"),
    ("NONE", "Aucune échéance"),
]


def _status(schedules, today):
    if not schedules:
        return "NONE"
    if all(schedule.remaining <= 0 for schedule in schedules):
        return "PAID"
    if any(schedule.remaining > 0 and schedule.due_date < today for schedule in schedules):
        return "LATE"
    if any(schedule.allocated > 0 for schedule in schedules):
        return "PARTIAL"
    return "DUE"


def build_rent_roll(organization, *, month, today=None):
    today = today or timezone.localdate()
    month = month.replace(day=1)
    ends = add_months(month, 1)

    unpaid_before = Q(due_date__lt=month, is_paid=False)
    in_month = Q(due_date__gte=month, due_date__lt=ends)
    schedules = (
        schedules_with_remaining(organization)
        .filter(unpaid_before | in_month, lease_contract__isnull=False)
        .order_by("due_date", "id")
    )
    current, arrears = defaultdict(list), defaultdict(list)
    for schedule in schedules:
        (arrears if schedule.due_date < month else current)[schedule.lease_contract_id].append(schedule)

    # Baux actifs, plus ceux qui sont terminés mais doivent encore quelque chose.
    leases = (
        LeaseContract.objects.filter(organization=organization)
        .filter(Q(status="ACTIVE") | Q(pk__in=[*current, *arrears]))
        .select_related("tenant", "unit__building__property")
        .annotate(last_reminder_at=Max("reminders__created_at"))
        .order_by("unit__building__property__name", "unit__reference", "id")
    )
    name = tenant_names(organization)
    emails = {
        user_id: email
        for user_id, email in Tenant.objects.filter(organization=organization).values_list("user_id", "email")
        if is_deliverable(email)
    }
    rows = []
    for lease in leases:
        month_rows, late_rows = current[lease.pk], arrears[lease.pk]
        if lease.status != "ACTIVE" and not late_rows and not month_rows:
            continue
        overdue = sum((s.remaining for s in late_rows), ZERO) + sum(
            (s.remaining for s in month_rows if s.due_date < today), ZERO
        )
        due = sum((s.amount_due for s in month_rows), ZERO)
        paid = sum((s.allocated for s in month_rows), ZERO)
        oldest = next((s.due_date for s in [*late_rows, *month_rows] if s.remaining > 0), None)
        rows.append({
            "lease": lease.pk,
            "lease_status": lease.status,
            "tenant": lease.tenant_id,
            "tenant_name": name(lease.tenant),
            "tenant_phone": lease.tenant.phone,
            "tenant_email": emails.get(lease.tenant_id, ""),
            "unit": lease.unit_id,
            "unit_reference": lease.unit.reference,
            "property": lease.unit.building.property_id,
            "property_name": lease.unit.building.property.name,
            "schedule": month_rows[0].pk if month_rows else None,
            "due_date": month_rows[0].due_date if month_rows else None,
            "due": due,
            "paid": paid,
            "remaining": due - paid,
            "arrears": sum((s.remaining for s in late_rows), ZERO),
            "overdue": overdue,
            "total_due": sum((s.remaining for s in [*late_rows, *month_rows]), ZERO),
            "oldest_unpaid": oldest,
            "days_late": max(0, (today - oldest).days) if oldest and overdue else 0,
            # Un arriéré met le bail en retard même si le loyer du mois est réglé ou à venir.
            "status": "LATE" if late_rows else _status(month_rows, today),
            "last_reminder_at": lease.last_reminder_at,
        })

    def total(key):
        return sum((row[key] for row in rows), ZERO)

    return {
        "month": month,
        "expected": total("due"),
        "collected": total("paid"),
        "remaining": total("remaining"),
        "overdue": total("overdue"),
        "counts": {code: sum(row["status"] == code for row in rows) for code, _ in RENT_STATUSES},
        "rows": rows,
    }
