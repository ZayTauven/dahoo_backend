from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404

from users.api.permissions import HasCapability
from properties.models import Property, Building, Unit
from .serializers import (
	PropertySerializer,
	PropertyCreateSerializer,
	BuildingSerializer,
	BuildingCreateSerializer,
	UnitSerializer,
	UnitCreateSerializer,
)


class PropertyListCreateAPIView(generics.ListCreateAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "property.view"
	queryset = Property.objects.all()

	def get_queryset(self):
		return Property.objects.filter(owner=self.request.user)

	def get_serializer_class(self):
		if self.request.method == "POST":
			return PropertyCreateSerializer
		return PropertySerializer

	def perform_create(self, serializer):
		serializer.save(owner=self.request.user)


class PropertyDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "property.view"
	queryset = Property.objects.all()
	serializer_class = PropertySerializer

	def get_object(self):
		return get_object_or_404(Property, pk=self.kwargs.get("pk"), owner=self.request.user)


class BuildingListCreateAPIView(generics.ListCreateAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "building.view"
	serializer_class = BuildingSerializer

	def get_queryset(self):
		property_pk = self.kwargs.get("property_pk")
		prop = get_object_or_404(Property, pk=property_pk, owner=self.request.user)
		return Building.objects.filter(property=prop)

	def perform_create(self, serializer):
		property_pk = self.kwargs.get("property_pk")
		prop = get_object_or_404(Property, pk=property_pk, owner=self.request.user)
		serializer.save(property=prop)


class BuildingDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "building.view"
	queryset = Building.objects.all()
	serializer_class = BuildingSerializer

	def get_object(self):
		return get_object_or_404(Building, pk=self.kwargs.get("pk"), property__owner=self.request.user)


class UnitListCreateAPIView(generics.ListCreateAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "unit.view"
	serializer_class = UnitSerializer

	def get_queryset(self):
		building_pk = self.kwargs.get("building_pk")
		building = get_object_or_404(Building, pk=building_pk, property__owner=self.request.user)
		return Unit.objects.filter(building=building)

	def perform_create(self, serializer):
		building_pk = self.kwargs.get("building_pk")
		building = get_object_or_404(Building, pk=building_pk, property__owner=self.request.user)
		serializer.save(building=building)


class UnitDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "unit.view"
	queryset = Unit.objects.all()
	serializer_class = UnitSerializer

	def get_object(self):
		return get_object_or_404(Unit, pk=self.kwargs.get("pk"), building__property__owner=self.request.user)


class UnitChangeStatusAPIView(APIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "unit.change_status"

	def post(self, request, pk):
		unit = get_object_or_404(Unit, pk=pk, building__property__owner=request.user)
		status_value = request.data.get("status")
		if status_value not in dict(Unit.STATUS_CHOICES):
			return Response({"detail": "Invalid status"}, status=status.HTTP_400_BAD_REQUEST)
		unit.status = status_value
		unit.save()
		return Response(UnitSerializer(unit).data)

