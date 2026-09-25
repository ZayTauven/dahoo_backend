"""
Notifications de l'espace connecté (cloche de l'en-tête).

- Événements (demande de visite, paiement, ticket, demande de démo) : notifications.signals.
- Rappels calculés (loyers en retard, fins de bail, fins d'essai) : sync_reminders, appelé au plus
  toutes les 15 minutes par agence quand un membre consulte ses notifications, ou par la commande
  `sync_notifications` (tâche planifiée). Une clé de dédoublonnage évite de notifier deux fois.

Les destinataires sont les membres actifs dont le rôle donne accès à l'écran concerné.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone

from notifications.models import InAppNotification

User = get_user_model()

SYNC_INTERVAL = 15 * 60
OVERDUE_WINDOW_DAYS = 90
LEASE_ENDING_DAYS = 30
TRIAL_ENDING_DAYS = 7
PLATFORM_TRIAL_DAYS = 3


def money(amount) -> str:
    """« 150 000 F CFA » (espace insécable, comme le front)."""
    value = int(Decimal(amount or 0).quantize(Decimal("1")))
    return f"{value:,}".replace(",", " ") + " F CFA"


def person_name(user) -> str:
    if user is None:
        return ""
    return f"{user.first_name} {user.last_name}".strip() or user.phone


def members_with(organization, capability):
    """Membres actifs de l'agence dont le rôle accorde `capability`."""
    return User.objects.filter(
        is_active=True,
        memberships__organization=organization,
        memberships__is_active=True,
        memberships__role__capabilities__code=capability,
    ).distinct()


def _create(users, *, organization, kind, title, body="", link="", dedupe_key=""):
    rows = [
        InAppNotification(
            user=user,
            organization=organization,
            kind=kind,
            title=title[:200],
            body=body,
            link=link,
            dedupe_key=dedupe_key,
        )
        for user in users
    ]
    # Rappel déjà envoyé à cet utilisateur (même clé) : ignoré en base, sans erreur.
    InAppNotification.objects.bulk_create(rows, ignore_conflicts=bool(dedupe_key))
    return len(rows)


def notify_members(organization, *, capability, kind, title, body="", link="", dedupe_key="", exclude=None):
    users = members_with(organization, capability)
    if exclude is not None:
        users = users.exclude(pk=exclude.pk)
    return _create(users, organization=organization, kind=kind, title=title, body=body, link=link, dedupe_key=dedupe_key)


def notify_user(user, *, organization, kind, title, body="", link=""):
    return _create([user], organization=organization, kind=kind, title=title, body=body, link=link)


def notify_platform_admins(*, kind, title, body="", link="", dedupe_key=""):
    users = User.objects.filter(is_active=True, is_staff=True)
    return _create(users, organization=None, kind=kind, title=title, body=body, link=link, dedupe_key=dedupe_key)


def _throttled(key, force):
    if force:
        return False
    # cache.add n'écrit que si la clé est absente : un seul calcul par intervalle.
    return not cache.add(key, True, SYNC_INTERVAL)


def sync_reminders(organization, *, today=None, force=False):
    """Loyers en retard, baux qui se terminent et fin d'essai de l'agence."""
    if _throttled(f"notifications:sync:{organization.pk}", force):
        return
    from analytics.dashboard import schedules_with_remaining
    from leases.models import LeaseContract
    from subscriptions.services import ACCESS_TRIAL, get_access_status

    today = today or timezone.localdate()

    overdue = (
        schedules_with_remaining(organization)
        .filter(
            is_paid=False,
            remaining__gt=0,
            due_date__lt=today,
            due_date__gte=today - timedelta(days=OVERDUE_WINDOW_DAYS),
            lease_contract__isnull=False,
        )
        .select_related("lease_contract__tenant", "lease_contract__unit")
        .order_by("due_date")
    )
    # Une notification par bail (total dû), renouvelée quand une nouvelle échéance passe en retard.
    by_lease = {}
    for schedule in overdue:
        by_lease.setdefault(schedule.lease_contract, []).append(schedule)
    for lease, schedules in by_lease.items():
        count = len(schedules)
        total = sum((schedule.remaining for schedule in schedules), Decimal(0))
        detail = f"{count} échéances · " if count > 1 else ""
        notify_members(
            organization,
            capability="payment.schedule.view",
            kind="RENT_OVERDUE",
            title=f"Loyer en retard : {person_name(lease.tenant)}",
            body=f"{lease.unit.reference} · {detail}{money(total)} dus depuis le {schedules[0].due_date:%d/%m/%Y}",
            link="/espace/echeances?etat=retard",
            dedupe_key=f"overdue:{lease.pk}:{schedules[-1].pk}",
        )

    ending = LeaseContract.objects.filter(
        organization=organization,
        status="ACTIVE",
        end_date__gte=today,
        end_date__lte=today + timedelta(days=LEASE_ENDING_DAYS),
    ).select_related("tenant", "unit")
    for lease in ending:
        days = (lease.end_date - today).days
        notify_members(
            organization,
            capability="lease.view",
            kind="LEASE_ENDING",
            title=f"Bail de {person_name(lease.tenant)} : fin dans {days} jour{'s' if days > 1 else ''}",
            body=f"{lease.unit.reference} · se termine le {lease.end_date:%d/%m/%Y}",
            link=f"/espace/baux/{lease.pk}",
            dedupe_key=f"lease-ending:{lease.pk}:{lease.end_date:%Y%m%d}",
        )

    if get_access_status(organization) == ACCESS_TRIAL:
        ends = timezone.localdate(organization.trial_ends_at)
        days = (ends - today).days
        if 0 <= days <= TRIAL_ENDING_DAYS:
            notify_members(
                organization,
                capability="organization.update",
                kind="TRIAL_ENDING",
                title=f"Votre essai se termine dans {days} jour{'s' if days > 1 else ''}" if days else "Votre essai se termine aujourd'hui",
                body="Activez un abonnement pour continuer à modifier vos données.",
                link="/espace/agence",
                dedupe_key=f"trial:{organization.pk}:{ends:%Y%m%d}",
            )


def sync_platform_reminders(*, today=None, force=False):
    """Équipe Dahoo : essais qui se terminent dans les 3 jours."""
    if _throttled("notifications:sync:platform", force):
        return
    from organizations.models import Organization
    from subscriptions.services import ACCESS_TRIAL, get_access_status

    today = today or timezone.localdate()
    now = timezone.now()
    candidates = Organization.objects.filter(
        is_active=True,
        is_internal=False,
        trial_ends_at__gte=now,
        trial_ends_at__lte=now + timedelta(days=PLATFORM_TRIAL_DAYS + 1),
    )
    for organization in candidates:
        if get_access_status(organization) != ACCESS_TRIAL:
            continue
        ends = timezone.localdate(organization.trial_ends_at)
        days = (ends - today).days
        if days > PLATFORM_TRIAL_DAYS:
            continue
        notify_platform_admins(
            kind="TRIAL_ENDING",
            title=f"Essai de {organization.name} : fin dans {days} jour{'s' if days > 1 else ''}" if days else f"Essai de {organization.name} : dernier jour",
            body="Sans abonnement, l'agence passera en lecture seule.",
            link=f"/plateforme/agences/{organization.pk}",
            dedupe_key=f"platform-trial:{organization.pk}:{ends:%Y%m%d}",
        )
