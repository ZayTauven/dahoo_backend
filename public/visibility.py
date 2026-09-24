"""
Règle de visibilité du portail public : seules les annonces publiées d'agences actives
dont l'accès n'est pas expiré (essai en cours, abonnement en cours ou organisation interne).
"""

from django.db.models import Count, Q

from listings.models import Listing
from listings.photos import with_cover
from organizations.models import Organization
from subscriptions.services import with_access

LISTINGS = "properties__buildings__units__listings"


def public_organizations():
    return with_access(Organization.objects.filter(is_active=True))


def public_listings():
    return Listing.objects.filter(
        status="PUBLISHED",
        unit__building__property__organization__in=public_organizations(),
    )


def listing_cards():
    """Annonces publiques prêtes à afficher (lot, bien, agence, couverture) sans requête par ligne."""
    return with_cover(public_listings().select_related("unit__building__property__organization"))


def similar_listings(listing, limit=3):
    """Autres annonces publiques du même type dans la même ville."""
    return (
        listing_cards()
        .filter(
            listing_type=listing.listing_type,
            unit__building__property__city__iexact=listing.unit.building.property.city,
        )
        .exclude(pk=listing.pk)
        .order_by("-published_at", "-id")[:limit]
    )


def public_agencies():
    """Agences visibles ayant au moins une annonce publiée, avec leurs compteurs."""
    published = Q(**{f"{LISTINGS}__status": "PUBLISHED"})
    return (
        public_organizations()
        .annotate(
            listings_count=Count(LISTINGS, filter=published, distinct=True),
            rent_count=Count(LISTINGS, filter=published & Q(**{f"{LISTINGS}__listing_type": "RENT"}), distinct=True),
            sale_count=Count(LISTINGS, filter=published & Q(**{f"{LISTINGS}__listing_type": "SALE"}), distinct=True),
        )
        .filter(listings_count__gt=0)
    )
