"""
API publique (portail d'annonces et vitrine SaaS) : sans authentification, limitée par IP.
La visibilité des annonces et des agences est centralisée dans public/visibility.py.
"""

from django.db.models import Count, Min, Q
from django.db.models.functions import Lower
from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle
from rest_framework.views import APIView

from listings.api.views import ProspectInterestCreateAPIView
from listings.models import Listing
from properties.models import Unit
from public.visibility import listing_cards, public_agencies, public_listings
from subscriptions.models import SubscriptionPlan

from .serializers import (
	DemoRequestSerializer,
	PublicAgencyDetailSerializer,
	PublicAgencySerializer,
	PublicListingDetailSerializer,
	PublicListingSerializer,
	PublicPlanSerializer,
	PublicStatsSerializer,
)

PROPERTY = "unit__building__property"


class PublicPagination(PageNumberPagination):
	page_size_query_param = "page_size"
	max_page_size = 50


class PublicAPIMixin:
	permission_classes = [AllowAny]
	authentication_classes = []
	throttle_classes = [AnonRateThrottle]


class PublicListingFilter(filters.FilterSet):
	listing_type = filters.ChoiceFilter(choices=Listing.LISTING_TYPE)
	city = filters.CharFilter(field_name=f"{PROPERTY}__city", lookup_expr="iexact")
	category = filters.ChoiceFilter(field_name="unit__category", choices=Unit.CATEGORY_CHOICES)
	min_price = filters.NumberFilter(field_name="price", lookup_expr="gte")
	max_price = filters.NumberFilter(field_name="price", lookup_expr="lte")
	min_bedrooms = filters.NumberFilter(field_name="unit__bedrooms", lookup_expr="gte")
	agency = filters.NumberFilter(field_name=f"{PROPERTY}__organization_id")
	q = filters.CharFilter(method="search", label="Recherche (titre, description, ville, quartier)")

	class Meta:
		model = Listing
		fields = []

	def search(self, queryset, name, value):
		value = value.strip()
		if not value:
			return queryset
		return queryset.filter(
			Q(title__icontains=value)
			| Q(description__icontains=value)
			| Q(**{f"{PROPERTY}__city__icontains": value})
			| Q(**{f"{PROPERTY}__neighborhood__icontains": value})
		)


class PublicListingListAPIView(PublicAPIMixin, generics.ListAPIView):
	"""Annonces publiques, filtrables et triables (`ordering` : price, -price, -published_at)."""

	serializer_class = PublicListingSerializer
	pagination_class = PublicPagination
	filterset_class = PublicListingFilter
	ordering_fields = ["price", "published_at"]
	ordering = ["-published_at", "-id"]

	def get_queryset(self):
		return listing_cards()


class PublicListingDetailAPIView(PublicAPIMixin, generics.RetrieveAPIView):
	"""Fiche d'une annonce : photos, position approximative, contact de l'agence et annonces similaires."""

	serializer_class = PublicListingDetailSerializer

	def get_queryset(self):
		return listing_cards().prefetch_related("photos")


class PublicListingInterestAPIView(ProspectInterestCreateAPIView):
	"""Demande de visite / d'information sur une annonce publique (crée ou retrouve le prospect)."""


class PublicAgencyListAPIView(PublicAPIMixin, generics.ListAPIView):
	serializer_class = PublicAgencySerializer
	pagination_class = PublicPagination

	def get_queryset(self):
		return public_agencies().order_by("-listings_count", "name")


class PublicAgencyDetailAPIView(PublicAPIMixin, generics.RetrieveAPIView):
	"""Fiche agence ; 404 si l'agence n'a aucune annonce publique."""

	serializer_class = PublicAgencyDetailSerializer

	def get_queryset(self):
		return public_agencies()


class PublicStatsAPIView(PublicAPIMixin, APIView):
	"""Compteurs pour l'accueil et les filtres du portail."""

	@extend_schema(responses=PublicStatsSerializer)
	def get(self, request):
		listings = public_listings().order_by()
		by_type = dict(listings.values_list("listing_type").annotate(count=Count("id")))
		by_category = dict(listings.values_list("unit__category").annotate(count=Count("id")))
		# Villes regroupées sans tenir compte de la casse ("Dakar" / "dakar").
		cities = (
			listings.exclude(**{f"{PROPERTY}__city": ""})
			.values(key=Lower(f"{PROPERTY}__city"))
			.annotate(city=Min(f"{PROPERTY}__city"), listings_count=Count("id"))
			.order_by("-listings_count", "city")
		)
		data = {
			"listings_count": sum(by_type.values()),
			"agencies_count": public_agencies().count(),
			"by_type": [
				{"listing_type": code, "label": label, "count": by_type.get(code, 0)}
				for code, label in Listing.LISTING_TYPE
			],
			"by_category": [
				{"category": code, "label": label, "count": by_category.get(code, 0)}
				for code, label in Unit.CATEGORY_CHOICES
			],
			"cities": [{"city": row["city"], "listings_count": row["listings_count"]} for row in cities],
		}
		return Response(PublicStatsSerializer(data).data)


class PublicPlanListAPIView(PublicAPIMixin, generics.ListAPIView):
	"""Offres d'abonnement actives (page tarifs de la vitrine)."""

	queryset = SubscriptionPlan.objects.filter(active=True).order_by("price", "id")
	serializer_class = PublicPlanSerializer
	pagination_class = None


class DemoRequestCreateAPIView(PublicAPIMixin, generics.CreateAPIView):
	"""Formulaire « demander une démo » de la vitrine (limité à quelques envois par heure et par IP)."""

	serializer_class = DemoRequestSerializer
	throttle_classes = [AnonRateThrottle, ScopedRateThrottle]
	throttle_scope = "demo_request"
