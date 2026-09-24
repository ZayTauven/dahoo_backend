from django.db.models import Case, IntegerField, OuterRef, Subquery, Value, When
from django.shortcuts import get_object_or_404
from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from access.permissions import IsStaffOrReadOnly
from maintenance.models import (
	MaintenanceAssignment,
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


PRIORITY_RANK = Case(
	*(When(priority=code, then=Value(rank)) for rank, (code, _) in enumerate(MaintenanceTicket.PRIORITY_CHOICES, start=1)),
	output_field=IntegerField(),
)


def tickets_with_labels():
	"""Tickets avec libellés, rang de gravité (tri) et affectation en cours, sans requête par ligne."""
	latest = MaintenanceAssignment.objects.filter(ticket=OuterRef("pk")).order_by("-assigned_at", "-id")
	return (
		MaintenanceTicket.objects.select_related("unit__building__property", "category", "reported_by")
		.annotate(
			priority_rank=PRIORITY_RANK,
			current_assignee_id=Subquery(latest.values("assigned_to_id")[:1]),
			current_assignee_first=Subquery(latest.values("assigned_to__first_name")[:1]),
			current_assignee_last=Subquery(latest.values("assigned_to__last_name")[:1]),
			current_assigned_at=Subquery(latest.values("assigned_at")[:1]),
		)
	)


class TicketFilter(filters.FilterSet):
	unit = filters.NumberFilter(field_name="unit_id")
	category = filters.NumberFilter(field_name="category_id")

	class Meta:
		model = MaintenanceTicket
		fields = ["status", "priority", "unit", "category"]


class MaintenanceTicketListCreateAPIView(OrganizationScopedMixin, generics.ListCreateAPIView):
	capability_resource = "maintenance.ticket"
	organization_lookup = TICKET_ORGANIZATION
	queryset = tickets_with_labels().order_by("-created_at")
	serializer_class = MaintenanceTicketSerializer
	filterset_class = TicketFilter
	search_fields = ["description", "unit__reference"]
	# priority_rank : ordre de gravité (Basse < Moyenne < Haute < Urgente), pas alphabétique.
	ordering_fields = ["created_at", "updated_at", "priority_rank", "status"]

	def perform_create(self, serializer):
		serializer.save(reported_by=self.request.user)


class MaintenanceTicketDetailAPIView(OrganizationScopedMixin, generics.RetrieveUpdateDestroyAPIView):
	capability_resource = "maintenance.ticket"
	organization_lookup = TICKET_ORGANIZATION
	queryset = tickets_with_labels()
	serializer_class = MaintenanceTicketSerializer


class MaintenanceTicketChangeStatusAPIView(OrganizationScopedMixin, APIView):
	required_capability = "maintenance.ticket.change_status"

	@extend_schema(request=TicketStatusSerializer, responses=MaintenanceTicketSerializer)
	def post(self, request, pk):
		ticket = get_object_or_404(tickets_with_labels(), pk=pk, **{TICKET_ORGANIZATION: self.organization})
		serializer = TicketStatusSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		ticket.status = serializer.validated_data["status"]
		ticket.save(update_fields=["status", "updated_at"])
		return Response(MaintenanceTicketSerializer(ticket, context={"request": request}).data)


class MaintenanceTicketAssignAPIView(OrganizationScopedMixin, APIView):
	required_capability = "maintenance.ticket.assign"

	@extend_schema(request=MaintenanceAssignmentSerializer, responses={201: MaintenanceAssignmentSerializer})
	def post(self, request, pk):
		ticket = get_object_or_404(tickets_with_labels(), pk=pk, **{TICKET_ORGANIZATION: self.organization})
		serializer = MaintenanceAssignmentSerializer(data=request.data, context={"request": request})
		serializer.is_valid(raise_exception=True)
		serializer.save(ticket=ticket, assigned_by=request.user)
		return Response(serializer.data, status=status.HTTP_201_CREATED)


class MaintenanceLogListCreateAPIView(OrganizationScopedMixin, generics.ListCreateAPIView):
	capability_resource = "maintenance.log"
	organization_lookup = "ticket__" + TICKET_ORGANIZATION
	queryset = MaintenanceLog.objects.select_related("user").order_by("created_at")
	serializer_class = MaintenanceLogSerializer

	def get_ticket(self):
		return get_object_or_404(MaintenanceTicket, pk=self.kwargs["pk"], **{TICKET_ORGANIZATION: self.organization})

	def get_queryset(self):
		return super().get_queryset().filter(ticket=self.get_ticket())

	def perform_create(self, serializer):
		serializer.save(ticket=self.get_ticket(), user=self.request.user)
