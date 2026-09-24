from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError

from subscriptions.models import Subscription

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
        "Votre période d'essai est terminée. Vos données restent consultables ; "
        "souscrivez un abonnement pour continuer à les modifier."
    )
    default_code = "subscription_required"


def get_active_subscription(organization):
    today = timezone.localdate()
    return (
        Subscription.objects.filter(organization=organization, status="ACTIVE", start_date__lte=today)
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=today))
        .select_related("plan")
        .order_by("-start_date")
        .first()
    )


def check_quota(organization, resource):
    """
    Refuse la création si la limite du plan actif est atteinte.
    Pendant l'essai (pas d'abonnement) ou avec une limite vide, aucune limite n'est appliquée :
    l'essai est borné dans le temps (voir get_access_status).
    """
    limit_field, count = QUOTAS[resource]
    subscription = get_active_subscription(organization)
    if subscription is None:
        return
    limit = getattr(subscription.plan, limit_field)
    if limit is not None and count(organization) >= limit:
        raise ValidationError(
            {"detail": f"Limite de votre abonnement atteinte ({limit} maximum). Passez à un plan supérieur."}
        )


def get_access_status(organization):
    """ACTIVE (abonnement en cours), TRIAL (essai en cours) ou EXPIRED (lecture seule)."""
    if get_active_subscription(organization) is not None:
        return ACCESS_ACTIVE
    if organization.trial_ends_at > timezone.now():
        return ACCESS_TRIAL
    return ACCESS_EXPIRED


def ensure_write_access(organization):
    if get_access_status(organization) == ACCESS_EXPIRED:
        raise SubscriptionRequired()
