from rest_framework import generics

from field_ops.models import DeliveryEvent, FieldEvent, GuardianProfile, VisitEvent
from organizations.scoping import OrganizationScopedMixin

from .serializers import (
	DeliveryEventSerializer,
	FieldEventSerializer,
	GuardianProfileSerializer,
	VisitEventSerializer,
)

EVENT_ORGANIZATION = "building__property__organization"


class GuardianProfileListCreateAPIView(OrganizationScopedMixin, generics.ListCreateAPIView):
	capability_resource = "field_ops.guardian"
	queryset = GuardianProfile.objects.prefetch_related("buildings").order_by("id")
	serializer_class = GuardianProfileSerializer

	def perform_create(self, serializer):
		serializer.save(organization=self.organization)


class GuardianProfileDetailAPIView(OrganizationScopedMixin, generics.RetrieveUpdateDestroyAPIView):
	capability_resource = "field_ops.guardian"
	queryset = GuardianProfile.objects.prefetch_related("buildings")
	serializer_class = GuardianProfileSerializer


class FieldEventListCreateAPIView(OrganizationScopedMixin, generics.ListCreateAPIView):
	capability_resource = "field_ops.event"
	organization_lookup = EVENT_ORGANIZATION
	queryset = FieldEvent.objects.order_by("-occurred_at")
	serializer_class = FieldEventSerializer

	def perform_create(self, serializer):
		serializer.save(recorded_by=self.request.user)


class FieldEventDetailAPIView(OrganizationScopedMixin, generics.RetrieveAPIView):
	capability_resource = "field_ops.event"
	organization_lookup = EVENT_ORGANIZATION
	queryset = FieldEvent.objects.all()
	serializer_class = FieldEventSerializer


class VisitEventDetailAPIView(OrganizationScopedMixin, generics.RetrieveAPIView):
	capability_resource = "field_ops.event"
	organization_lookup = "field_event__" + EVENT_ORGANIZATION
	queryset = VisitEvent.objects.all()
	serializer_class = VisitEventSerializer


class DeliveryEventDetailAPIView(OrganizationScopedMixin, generics.RetrieveAPIView):
	capability_resource = "field_ops.event"
	organization_lookup = "field_event__" + EVENT_ORGANIZATION
	queryset = DeliveryEvent.objects.all()
	serializer_class = DeliveryEventSerializer
