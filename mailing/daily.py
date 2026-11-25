"""Envois quotidiens (commande `sync_notifications`) : rappels aux locataires choisis par l'agence, point du jour."""

from datetime import timedelta

from django.utils import timezone

from analytics.dashboard import schedules_with_remaining
from mailing.agency import email_rent_due, email_rent_overdue
from mailing.subscriptions import email_subscription_ended, email_subscription_ending
from mailing.team import email_trial_ending, send_digests
from payments.models import RentReminder
from payments.reminders import reminder_for
from rest_framework.exceptions import ValidationError
from subscriptions.services import ACCESS_EXPIRED, ACCESS_TRIAL, get_access_status, get_active_subscription

DUE_BEFORE_DAYS = 3
# Relances automatiques : 5 puis 15 jours après l'échéance.
OVERDUE_AFTER_DAYS = (15, 5)
TRIAL_DAYS = (7, 1)
SUBSCRIPTION_DAYS = (7, 1)


def send_due_reminders(organization, *, today):
    """Trois jours avant l'échéance. La fenêtre rattrape un jour sans exécution, la clé évite les doublons."""
    schedules = (
        schedules_with_remaining(organization)
        .filter(
            schedule_type="RENT", is_paid=False, remaining__gt=0, lease_contract__status="ACTIVE",
            due_date__gt=today, due_date__lte=today + timedelta(days=DUE_BEFORE_DAYS),
        )
        .select_related("organization", "lease_contract__tenant", "lease_contract__organization", "lease_contract__unit__building__property")
    )
    for schedule in schedules:
        email_rent_due(schedule, schedule.remaining, dedupe_key=f"due:{schedule.pk}")


def send_overdue_reminders(organization, *, today):
    """Une relance par échéance et par palier ; un même bail n'en reçoit qu'une par jour."""
    schedules = (
        schedules_with_remaining(organization)
        .filter(
            schedule_type="RENT", is_paid=False, remaining__gt=0, lease_contract__status="ACTIVE",
            due_date__lte=today - timedelta(days=min(OVERDUE_AFTER_DAYS)),
            # Pas de rafale sur de vieux impayés le jour où l'agence active les relances.
            due_date__gte=today - timedelta(days=30),
        )
        .select_related("lease_contract__tenant", "lease_contract__organization", "lease_contract__unit__building__property")
        .order_by("-due_date")
    )
    reminded = set()
    for schedule in schedules:
        lease = schedule.lease_contract
        step = next(step for step in OVERDUE_AFTER_DAYS if (today - schedule.due_date).days >= step)
        if lease.pk in reminded:
            continue
        try:
            reminder = reminder_for(lease, today=today)
        except ValidationError:
            continue
        if email_rent_overdue(lease, reminder, strict=False, dedupe_key=f"overdue:{schedule.pk}:{step}"):
            reminded.add(lease.pk)
            RentReminder.objects.create(
                organization=organization, lease=lease, channel="EMAIL", amount=reminder["amount"], message=reminder["message"],
            )


def run_daily(organization, *, today=None):
    today = today or timezone.localdate()
    status = get_access_status(organization)
    if status == ACCESS_TRIAL:
        ends = timezone.localdate(organization.trial_ends_at)
        if (ends - today).days in TRIAL_DAYS:
            email_trial_ending(organization, ends)
    subscription = get_active_subscription(organization)
    if subscription and subscription.end_date and (subscription.end_date - today).days in SUBSCRIPTION_DAYS:
        email_subscription_ending(subscription)
    if status == ACCESS_EXPIRED:
        ended = organization.subscriptions.filter(status="ACTIVE", end_date=today - timedelta(days=1)).select_related("plan").first()
        if ended:
            email_subscription_ended(ended)
    # Essai terminé sans abonnement : l'espace est en lecture seule, Dahoo n'écrit plus à sa place.
    if status == ACCESS_EXPIRED:
        return
    if organization.email_due_reminders:
        send_due_reminders(organization, today=today)
    if organization.email_overdue_reminders:
        send_overdue_reminders(organization, today=today)
    send_digests(organization, today=today)
