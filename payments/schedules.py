"""
Échéancier automatique des baux.

Un bail découpe le temps en périodes calendaires (un mois, ou trois pour un bail trimestriel) qui
commencent le 1er du mois de début du bail. Le loyer de chaque période (loyer + charges) est dû le
`due_day` du premier mois ; une période entamée par le début ou la fin du bail est facturée au prorata
des jours occupés et due au plus tôt le jour d'entrée.

Les échéances ne sont pas toutes créées d'avance : chacune l'est au plus `HORIZON_DAYS` jours avant
sa date, à l'activation du bail puis par `extend_schedules` (appelé avec les rappels, voir
notifications.services.sync_reminders). Une période qui contient déjà un loyer, saisi à la main ou
non, est sautée.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from analytics.dashboard import add_months
from payments.models import PaymentSchedule

HORIZON_DAYS = 31


@dataclass(frozen=True)
class Period:
    starts: date  # 1er jour de la période calendaire
    ends: date  # lendemain du dernier jour
    due_date: date
    amount: Decimal
    prorated: bool


def period_months(lease):
    return 3 if lease.payment_frequency == "QUARTERLY" else 1


def lease_periods(lease, *, until):
    """Périodes du bail dont le loyer est dû au plus tard le `until`, dans l'ordre."""
    months = period_months(lease)
    full_amount = (lease.rent_amount + lease.charges_amount) * months
    lease_ends = lease.end_date + timedelta(days=1) if lease.end_date else None
    starts = lease.start_date.replace(day=1)
    while lease_ends is None or starts < lease_ends:
        ends = add_months(starts, months)
        occupied_from = max(starts, lease.start_date)
        occupied_to = min(ends, lease_ends) if lease_ends else ends
        due_date = min(max(starts.replace(day=lease.due_day), occupied_from), occupied_to - timedelta(days=1))
        if due_date > until:
            return
        prorated = (occupied_from, occupied_to) != (starts, ends)
        amount = full_amount
        if prorated:
            share = Decimal((occupied_to - occupied_from).days) / Decimal((ends - starts).days)
            amount = (full_amount * share).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        yield Period(starts, ends, due_date, amount, prorated)
        starts = ends


def pending_periods(lease, *, schedules_from, today=None):
    """Périodes à créer : commencées à partir de `schedules_from`, dues d'ici l'horizon, sans loyer existant."""
    today = today or timezone.localdate()
    existing = list(lease.schedules.filter(schedule_type="RENT").values_list("due_date", flat=True))
    return [
        period
        for period in lease_periods(lease, until=today + timedelta(days=HORIZON_DAYS))
        if max(period.starts, lease.start_date) >= schedules_from
        and not any(period.starts <= due <= period.ends - timedelta(days=1) for due in existing)
    ]


def current_period_start(lease, today=None):
    """Début de la période en cours (ou de la première, si le bail n'a pas commencé)."""
    today = today or timezone.localdate()
    current = lease.start_date
    for period in lease_periods(lease, until=date.max):
        if period.starts > today:
            break
        current = max(period.starts, lease.start_date)
    return current


def generate_schedules(lease, *, today=None):
    """Crée les loyers dus d'ici l'horizon pour un bail actif à échéancier automatique."""
    if not lease.auto_schedules or lease.status != "ACTIVE":
        return []
    periods = pending_periods(lease, schedules_from=lease.schedules_from or lease.start_date, today=today)
    return PaymentSchedule.objects.bulk_create(
        PaymentSchedule(
            organization_id=lease.organization_id,
            lease_contract=lease,
            schedule_type="RENT",
            due_date=period.due_date,
            amount_due=period.amount,
        )
        for period in periods
    )


@transaction.atomic
def enable_auto_schedules(lease, *, schedules_from, today=None):
    from leases.models import LeaseContract

    lease = LeaseContract.objects.select_for_update().get(pk=lease.pk)
    lease.auto_schedules = True
    lease.schedules_from = schedules_from
    lease.save(update_fields=["auto_schedules", "schedules_from"])
    return lease, generate_schedules(lease, today=today)


def disable_auto_schedules(lease):
    lease.auto_schedules = False
    lease.save(update_fields=["auto_schedules"])
    return lease


def extend_schedules(organization, *, today=None):
    """Prolonge l'échéancier de tous les baux actifs automatiques de l'agence. Renvoie le nombre créé."""
    from leases.models import LeaseContract

    leases = LeaseContract.objects.filter(organization=organization, status="ACTIVE", auto_schedules=True)
    return sum(len(generate_schedules(lease, today=today)) for lease in leases)


def drop_future_schedules(lease, *, today=None):
    """À la fin anticipée d'un bail automatique : supprime les loyers à venir qu'aucun paiement ne touche."""
    if not lease.auto_schedules:
        return 0
    today = today or timezone.localdate()
    deleted, _ = lease.schedules.filter(
        schedule_type="RENT", due_date__gt=today, allocations__isnull=True
    ).delete()
    return deleted


def preview_auto_schedules(lease, *, today=None):
    """Ce que créerait l'échéancier : depuis le début du bail, ou depuis la période en cours."""
    today = today or timezone.localdate()

    def option(schedules_from):
        periods = pending_periods(lease, schedules_from=schedules_from, today=today)
        return {
            "schedules_from": schedules_from,
            "count": len(periods),
            "total": sum((period.amount for period in periods), Decimal("0")),
            "first_due": periods[0].due_date if periods else None,
            "prorated": any(period.prorated for period in periods),
        }

    from_start = option(lease.start_date)
    current = current_period_start(lease, today)
    from_current = option(current) if current > lease.start_date else None
    # Périodes passées déjà saisies : les deux choix reviennent au même, un seul est proposé.
    if from_current and from_current["count"] == from_start["count"]:
        from_current = None
    return {"from_start": from_start, "from_current": from_current, "horizon_days": HORIZON_DAYS}
