from rest_framework.exceptions import ValidationError

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


def get_active_subscription(organization):
    return (
        Subscription.objects.filter(organization=organization, status="ACTIVE")
        .select_related("plan")
        .order_by("-start_date")
        .first()
    )


def check_quota(organization, resource):
    """
    Refuse la création si la limite du plan actif est atteinte.
    Sans abonnement actif, ou avec une limite vide, aucune limite n'est appliquée.
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
