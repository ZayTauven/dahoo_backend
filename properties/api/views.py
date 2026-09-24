from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from organizations.scoping import OrganizationScopedMixin
from properties.models import Building, Property, Unit
from subscriptions.services import check_quota

from .serializers import BuildingSerializer, PropertySerializer, UnitSerializer, UnitStatusSerializer

UNIT_ORGANIZATION = "building__property__organization"


def properties_with_counts():
	return Property.objects.annotate(
		buildings_count=Count("buildings", distinct=True),
		units_count=Count("buildings__units", distinct=True),
		occupied_units_count=Count("buildings__units", filter=Q(buildings__units__status="RENTED"), distinct=True),
	)


class PropertyFilter(filters.FilterSet):
	city = filters.CharFilter(lookup_expr="iexact")

	class Meta:
		model = Property
		fields = ["city"]


class PropertyListCreateAPIView(OrganizationScopedMixin, generics.ListCreateAPIView):
	capability_resource = "property"
	queryset = properties_with_counts().order_by("-created_at")
	serializer_class = PropertySerializer
	filterset_class = PropertyFilter
	search_fields = ["name", "address", "city", "neighborhood"]
	ordering_fields = ["name", "city", "created_at", "units_count"]

	def perform_create(self, serializer):
		check_quota(self.organization, "property")
		serializer.save(organization=self.organization)


class PropertyDetailAPIView(OrganizationScopedMixin, generics.RetrieveUpdateDestroyAPIView):
	capability_resource = "property"
	queryset = properties_with_counts()
	serializer_class = PropertySerializer


class BuildingListCreateAPIView(OrganizationScopedMixin, generics.ListCreateAPIView):
	capability_resource = "building"
	organization_lookup = "property__organization"
	queryset = Building.objects.order_by("name")
	serializer_class = BuildingSerializer

	def get_property(self):
		return get_object_or_404(Property, pk=self.kwargs["property_pk"], organization=self.organization)

	def get_queryset(self):
		return super().get_queryset().filter(property=self.get_property())

	def perform_create(self, serializer):
		serializer.save(property=self.get_property())


class BuildingDetailAPIView(OrganizationScopedMixin, generics.RetrieveUpdateDestroyAPIView):
	capability_resource = "building"
	organization_lookup = "property__organization"
	queryset = Building.objects.all()
	serializer_class = BuildingSerializer


class UnitFilter(filters.FilterSet):
	# Identifiants en simples nombres : pas de requête de validation sur les autres organisations.
	building = filters.NumberFilter(field_name="building_id")
	property = filters.NumberFilter(field_name="building__property_id")

	class Meta:
		model = Unit
		fields = ["status", "category", "building", "property"]


class UnitListAPIView(OrganizationScopedMixin, generics.ListAPIView):
	"""Tous les lots de l'organisation (sélecteurs des formulaires bail, ticket, annonce)."""

	capability_resource = "unit"
	organization_lookup = UNIT_ORGANIZATION
	queryset = Unit.objects.select_related("building__property").order_by(
		"building__property__name", "building__name", "reference"
	)
	serializer_class = UnitSerializer
	filterset_class = UnitFilter
	search_fields = ["reference", "unit_type", "building__name", "building__property__name"]
	ordering_fields = ["reference", "surface", "status"]


class UnitListCreateAPIView(OrganizationScopedMixin, generics.ListCreateAPIView):
	capability_resource = "unit"
	organization_lookup = UNIT_ORGANIZATION
	queryset = Unit.objects.select_related("building__property").order_by("reference")
	serializer_class = UnitSerializer
	filterset_fields = ["status", "category"]
	search_fields = ["reference", "unit_type"]
	ordering_fields = ["reference", "surface", "status"]

	def get_building(self):
		return get_object_or_404(
			Building, pk=self.kwargs["building_pk"], property__organization=self.organization
		)

	def get_queryset(self):
		return super().get_queryset().filter(building=self.get_building())

	def perform_create(self, serializer):
		building = self.get_building()
		check_quota(self.organization, "unit")
		serializer.save(building=building)


class UnitDetailAPIView(OrganizationScopedMixin, generics.RetrieveUpdateDestroyAPIView):
	capability_resource = "unit"
	organization_lookup = UNIT_ORGANIZATION
	queryset = Unit.objects.select_related("building__property")
	serializer_class = UnitSerializer


class UnitChangeStatusAPIView(OrganizationScopedMixin, APIView):
	required_capability = "unit.change_status"

	@extend_schema(request=UnitStatusSerializer, responses=UnitSerializer)
	def post(self, request, pk):
		unit = get_object_or_404(
			Unit.objects.select_related("building__property"), pk=pk, **{UNIT_ORGANIZATION: self.organization}
		)
		serializer = UnitStatusSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		unit.status = serializer.validated_data["status"]
		unit.save(update_fields=["status"])
		return Response(UnitSerializer(unit).data)
