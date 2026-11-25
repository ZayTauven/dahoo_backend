from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError

from subscriptions.models import Subscription, SubscriptionPlan

# Ressource -> (champ de limite du plan, fonction de comptage)
QUOTAS = {
    "property": ("max_properties", lambda org: org.properties.count()),
    "unit": ("max_units", lambda org: _count_units(org)),
    "member": ("max_users", lambda org: org.memberships.filter(is_active=True).count()),
}


def _count_units(organization):
    from properties.models import Unit

    return Unit.objects.filter(building__property__organization=organization).count()


ACCESS_ACTIVE = "ACTIVE"
ACCESS_TRIAL = "TRIAL"
ACCESS_EXPIRED = "EXPIRED"


class SubscriptionRequired(APIException):
    status_code = status.HTTP_402_PAYMENT_REQUIRED
    default_detail = (
        "Votre essai ou votre abonnement est terminé. Vos données restent consultables ; "
        "réglez un abonnement pour continuer à les modifier."
    )
    default_code = "subscription_required"


def active_subscriptions():
    """Abonnements en cours aujourd'hui (actifs, commencés, non terminés)."""
    today = timezone.localdate()
    return Subscription.objects.filter(status="ACTIVE", start_date__lte=today).filter(
        Q(end_date__isnull=True) | Q(end_date__gte=today)
    )


def get_active_subscription(organization):
    return (
        active_subscriptions()
        .filter(organization=organization)
        .select_related("plan")
        .order_by("-start_date", "-id")
        .first()
    )


def check_quota(organization, resource):
    """Refuse la création si la limite de l'offre (ou de l'essai) est atteinte ; une limite vide ne bloque rien."""
    limit, trial = _limit(organization, resource)
    if limit is None or QUOTAS[resource][1](organization) < limit:
        return
    if trial:
        detail = f"Limite de l'essai atteinte ({limit} maximum). Choisissez une offre pour aller plus loin."
    else:
        detail = f"Limite de votre abonnement atteinte ({limit} maximum). Passez à un plan supérieur."
    raise ValidationError({"detail": detail})


def remaining_quota(organization, resource):
    """Nombre de créations encore permises par l'offre, ou None si rien ne les limite."""
    limit, _ = _limit(organization, resource)
    return None if limit is None else max(0, limit - QUOTAS[resource][1](organization))


def limiting_plan(organization):
    """Offre dont les limites s'appliquent, et si c'est au titre de l'essai."""
    subscription = get_active_subscription(organization)
    if subscription is not None:
        return subscription.plan, False
    if organization.is_internal:
        return None, False
    return SubscriptionPlan.objects.filter(limits_trial=True).first(), True


def _limit(organization, resource):
    plan, trial = limiting_plan(organization)
    return (getattr(plan, QUOTAS[resource][0]) if plan else None), trial


USAGE_LABELS = {"property": "Biens", "unit": "Lots", "member": "Utilisateurs"}


def build_usage(organization, plan):
    """Consommation de l'agence face aux limites d'une offre (None : sans limite)."""
    return [
        {"resource": resource, "label": USAGE_LABELS[resource], "used": count(organization), "limit": getattr(plan, field) if plan else None}
        for resource, (field, count) in QUOTAS.items()
    ]


def get_access_status(organization):
    """ACTIVE (abonnement en cours), TRIAL (essai en cours) ou EXPIRED (lecture seule)."""
    if organization.is_internal or get_active_subscription(organization) is not None:
        return ACCESS_ACTIVE
    if organization.trial_ends_at > timezone.now():
        return ACCESS_TRIAL
    return ACCESS_EXPIRED


def with_access(organizations):
    """
    Filtre en base équivalent à `get_access_status(org) != EXPIRED` : organisation interne,
    essai en cours ou abonnement en cours (utilisé par le portail public).
    """
    return organizations.filter(
        Q(is_internal=True)
        | Q(trial_ends_at__gt=timezone.now())
        | Q(pk__in=active_subscriptions().values("organization"))
    )


def ensure_write_access(organization):
    if get_access_status(organization) == ACCESS_EXPIRED:
        raise SubscriptionRequired()
