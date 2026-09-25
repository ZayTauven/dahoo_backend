"""
Recherche globale de l'espace agence (palette de commandes, Ctrl+K) : biens, lots, locataires, baux,
annonces et tickets de l'agence active, limités aux types que le rôle a le droit de consulter.
Chaque résultat porte le chemin de l'écran à ouvrir dans le front.
"""

from functools import reduce
from operator import and_, or_
from urllib.parse import urlencode

from django.db.models import Q
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from access.permissions import HasCapability, get_membership_capabilities
from leases.models import LeaseContract, Tenant
from listings.models import Listing
from maintenance.models import MaintenanceTicket
from notifications.services import person_name
from properties.models import Property, Unit

RESULT_TYPES = ["property", "unit", "tenant", "lease", "listing", "ticket"]
MIN_LENGTH = 2
PER_TYPE = 5


class SearchResultSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=RESULT_TYPES)
    id = serializers.IntegerField()
    title = serializers.CharField()
    subtitle = serializers.CharField()
    link = serializers.CharField(help_text="Chemin de l'écran dans le front.")


class SearchResponseSerializer(serializers.Serializer):
    query = serializers.CharField()
    results = SearchResultSerializer(many=True)


def matching(fields, terms):
    """
    Chaque mot doit apparaître dans au moins un des champs (« awa diop » trouve Awa Diop), sans tenir
    compte des accents ni de la casse (« aissatou » trouve Aïssatou ; extension unaccent).
    """
    return reduce(and_, (reduce(or_, (Q(**{f"{field}__unaccent__icontains": term}) for field in fields)) for term in terms))


def _properties(org, terms):
    rows = Property.objects.filter(matching(["name", "address", "city", "neighborhood"], terms), organization=org)
    for item in rows.order_by("name")[:PER_TYPE]:
        place = ", ".join(part for part in (item.neighborhood, item.city) if part)
        yield "property", item.pk, item.name, place, f"/espace/biens/{item.pk}"


def _units(org, terms):
    rows = Unit.objects.filter(
        matching(["reference", "unit_type", "building__name", "building__property__name"], terms),
        building__property__organization=org,
    ).select_related("building__property")
    for unit in rows.order_by("reference")[:PER_TYPE]:
        prop = unit.building.property
        subtitle = " · ".join(part for part in (prop.name, unit.get_category_display(), unit.get_status_display()) if part)
        yield "unit", unit.pk, f"Lot {unit.reference}", subtitle, f"/espace/biens/{prop.pk}"


def _tenants(org, terms):
    rows = Tenant.objects.filter(matching(["first_name", "last_name", "email", "user__phone"], terms), organization=org)
    for tenant in rows.select_related("user").order_by("last_name", "first_name")[:PER_TYPE]:
        name = f"{tenant.first_name} {tenant.last_name}".strip()
        query = urlencode({"search": tenant.user.phone or name})
        yield "tenant", tenant.pk, name, tenant.user.phone, f"/espace/locataires?{query}"


def _leases(org, terms):
    rows = LeaseContract.objects.filter(
        matching(["tenant__first_name", "tenant__last_name", "tenant__phone", "unit__reference"], terms),
        organization=org,
    ).select_related("tenant", "unit")
    for lease in rows.order_by("-start_date")[:PER_TYPE]:
        subtitle = f"{lease.unit.reference} · {lease.get_status_display()}"
        yield "lease", lease.pk, f"Bail de {person_name(lease.tenant)}", subtitle, f"/espace/baux/{lease.pk}"


def _listings(org, terms):
    rows = Listing.objects.filter(matching(["title", "unit__reference"], terms), unit__building__property__organization=org)
    for listing in rows.select_related("unit").order_by("-created_at")[:PER_TYPE]:
        subtitle = f"{listing.get_listing_type_display()} · {listing.get_status_display()}"
        yield "listing", listing.pk, listing.title, subtitle, f"/espace/annonces/{listing.pk}"


def _tickets(org, terms):
    rows = MaintenanceTicket.objects.filter(
        matching(["description", "unit__reference", "category__label"], terms), unit__building__property__organization=org
    ).select_related("unit", "category")
    for ticket in rows.order_by("-created_at")[:PER_TYPE]:
        category = ticket.category.label if ticket.category else "Maintenance"
        title = f"{category} : {ticket.unit.reference}"
        subtitle = f"{ticket.get_status_display()} · {ticket.description[:80]}"
        yield "ticket", ticket.pk, title, subtitle, f"/espace/maintenance/{ticket.pk}"


SOURCES = [
    ("property.view", _properties),
    ("unit.view", _units),
    ("tenant.view", _tenants),
    ("lease.view", _leases),
    ("listing.view", _listings),
    ("maintenance.ticket.view", _tickets),
]


class SearchAPIView(APIView):
    permission_classes = [HasCapability]

    @extend_schema(
        parameters=[OpenApiParameter("q", OpenApiTypes.STR, description=f"Au moins {MIN_LENGTH} caractères.")],
        responses=SearchResponseSerializer,
    )
    def get(self, request):
        query = " ".join(request.query_params.get("q", "").split())[:100]
        terms = query.split()
        results = []
        if len(query) >= MIN_LENGTH:
            granted = get_membership_capabilities(request)
            for capability, source in SOURCES:
                if request.user.is_superuser or capability in granted:
                    results += [
                        {"type": kind, "id": pk, "title": title, "subtitle": subtitle or "", "link": link}
                        for kind, pk, title, subtitle, link in source(request.organization, terms)
                    ]
        return Response({"query": query, "results": results})
