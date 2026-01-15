from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404

from users.api.permissions import HasCapability
from field_ops.models import GuardianProfile, FieldEvent, VisitEvent, DeliveryEvent
from .serializers import (
	GuardianProfileSerializer,
	FieldEventSerializer,
	FieldEventCreateSerializer,
	VisitEventSerializer,
	DeliveryEventSerializer,
)


class GuardianProfileListCreateAPIView(generics.ListCreateAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "field_ops.guardian.view"
	queryset = GuardianProfile.objects.all()
	serializer_class = GuardianProfileSerializer


class GuardianProfileDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "field_ops.guardian.view"
	queryset = GuardianProfile.objects.all()
	serializer_class = GuardianProfileSerializer


class FieldEventListCreateAPIView(generics.ListCreateAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "field_ops.event.view"

	def get_queryset(self):
		return FieldEvent.objects.filter(recorded_by=self.request.user)

	def get_serializer_class(self):
		if self.request.method == "POST":
			return FieldEventCreateSerializer
		return FieldEventSerializer


class FieldEventDetailAPIView(generics.RetrieveAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "field_ops.event.view"
	queryset = FieldEvent.objects.all()
	serializer_class = FieldEventSerializer


class VisitEventDetailAPIView(generics.RetrieveAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "field_ops.event.view"
	queryset = VisitEvent.objects.all()
	serializer_class = VisitEventSerializer


class DeliveryEventDetailAPIView(generics.RetrieveAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "field_ops.event.view"
	queryset = DeliveryEvent.objects.all()
	serializer_class = DeliveryEventSerializer

