from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from organizations.scoping import OrganizationScopedMixin
from properties.models import Building, Property, Unit
from subscriptions.services import check_quota

from .serializers import BuildingSerializer, PropertySerializer, UnitSerializer, UnitStatusSerializer


class PropertyListCreateAPIView(OrganizationScopedMixin, generics.ListCreateAPIView):
	capability_resource = "property"
	queryset = Property.objects.order_by("-created_at")
	serializer_class = PropertySerializer

	def perform_create(self, serializer):
		check_quota(self.organization, "property")
		serializer.save(organization=self.organization)


class PropertyDetailAPIView(OrganizationScopedMixin, generics.RetrieveUpdateDestroyAPIView):
	capability_resource = "property"
	queryset = Property.objects.all()
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


class UnitListCreateAPIView(OrganizationScopedMixin, generics.ListCreateAPIView):
	capability_resource = "unit"
	organization_lookup = "building__property__organization"
	queryset = Unit.objects.order_by("reference")
	serializer_class = UnitSerializer

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
	organization_lookup = "building__property__organization"
	queryset = Unit.objects.all()
	serializer_class = UnitSerializer


class UnitChangeStatusAPIView(OrganizationScopedMixin, APIView):
	required_capability = "unit.change_status"

	@extend_schema(request=UnitStatusSerializer, responses=UnitSerializer)
	def post(self, request, pk):
		unit = get_object_or_404(Unit, pk=pk, building__property__organization=self.organization)
		serializer = UnitStatusSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		unit.status = serializer.validated_data["status"]
		unit.save(update_fields=["status"])
		return Response(UnitSerializer(unit).data)
