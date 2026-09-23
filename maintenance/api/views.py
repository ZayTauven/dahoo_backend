from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from access.permissions import IsStaffOrReadOnly
from maintenance.models import (
	MaintenanceCategory,
	MaintenanceLog,
	MaintenanceTicket,
)
from organizations.scoping import OrganizationScopedMixin

from .serializers import (
	MaintenanceAssignmentSerializer,
	MaintenanceCategorySerializer,
	MaintenanceLogSerializer,
	MaintenanceTicketSerializer,
	TicketStatusSerializer,
)

TICKET_ORGANIZATION = "unit__building__property__organization"


# Catégories : référentiel commun (plomberie, électricité...), modifiable par le staff Dahoo.
class MaintenanceCategoryListCreateAPIView(generics.ListCreateAPIView):
	permission_classes = [IsStaffOrReadOnly]
	queryset = MaintenanceCategory.objects.order_by("label")
	serializer_class = MaintenanceCategorySerializer
	pagination_class = None


class MaintenanceCategoryDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
	permission_classes = [IsStaffOrReadOnly]
	queryset = MaintenanceCategory.objects.all()
	serializer_class = MaintenanceCategorySerializer


class MaintenanceTicketListCreateAPIView(OrganizationScopedMixin, generics.ListCreateAPIView):
	capability_resource = "maintenance.ticket"
	organization_lookup = TICKET_ORGANIZATION
	queryset = MaintenanceTicket.objects.order_by("-created_at")
	serializer_class = MaintenanceTicketSerializer

	def perform_create(self, serializer):
		serializer.save(reported_by=self.request.user)


class MaintenanceTicketDetailAPIView(OrganizationScopedMixin, generics.RetrieveUpdateDestroyAPIView):
	capability_resource = "maintenance.ticket"
	organization_lookup = TICKET_ORGANIZATION
	queryset = MaintenanceTicket.objects.all()
	serializer_class = MaintenanceTicketSerializer


class MaintenanceTicketChangeStatusAPIView(OrganizationScopedMixin, APIView):
	required_capability = "maintenance.ticket.change_status"

	@extend_schema(request=TicketStatusSerializer, responses=MaintenanceTicketSerializer)
	def post(self, request, pk):
		ticket = get_object_or_404(MaintenanceTicket, pk=pk, **{TICKET_ORGANIZATION: self.organization})
		serializer = TicketStatusSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		ticket.status = serializer.validated_data["status"]
		ticket.save(update_fields=["status", "updated_at"])
		return Response(MaintenanceTicketSerializer(ticket, context={"request": request}).data)


class MaintenanceTicketAssignAPIView(OrganizationScopedMixin, APIView):
	required_capability = "maintenance.ticket.assign"

	@extend_schema(request=MaintenanceAssignmentSerializer, responses={201: MaintenanceAssignmentSerializer})
	def post(self, request, pk):
		ticket = get_object_or_404(MaintenanceTicket, pk=pk, **{TICKET_ORGANIZATION: self.organization})
		serializer = MaintenanceAssignmentSerializer(data=request.data, context={"request": request})
		serializer.is_valid(raise_exception=True)
		serializer.save(ticket=ticket, assigned_by=request.user)
		return Response(serializer.data, status=status.HTTP_201_CREATED)


class MaintenanceLogListCreateAPIView(OrganizationScopedMixin, generics.ListCreateAPIView):
	capability_resource = "maintenance.log"
	organization_lookup = "ticket__" + TICKET_ORGANIZATION
	queryset = MaintenanceLog.objects.order_by("created_at")
	serializer_class = MaintenanceLogSerializer

	def get_ticket(self):
		return get_object_or_404(MaintenanceTicket, pk=self.kwargs["pk"], **{TICKET_ORGANIZATION: self.organization})

	def get_queryset(self):
		return super().get_queryset().filter(ticket=self.get_ticket())

	def perform_create(self, serializer):
		serializer.save(ticket=self.get_ticket(), user=self.request.user)
