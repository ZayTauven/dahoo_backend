from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404

from users.api.permissions import HasCapability
from maintenance.models import (
	MaintenanceCategory,
	MaintenanceTicket,
	MaintenanceAssignment,
	MaintenanceLog,
)
from .serializers import (
	MaintenanceCategorySerializer,
	MaintenanceTicketSerializer,
	MaintenanceTicketCreateSerializer,
	MaintenanceAssignmentSerializer,
	MaintenanceLogSerializer,
)


class MaintenanceCategoryListCreateAPIView(generics.ListCreateAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "maintenance.category.view"
	queryset = MaintenanceCategory.objects.all()
	serializer_class = MaintenanceCategorySerializer


class MaintenanceCategoryDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "maintenance.category.view"
	queryset = MaintenanceCategory.objects.all()
	serializer_class = MaintenanceCategorySerializer


class MaintenanceTicketListCreateAPIView(generics.ListCreateAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "maintenance.ticket.view"

	def get_queryset(self):
		user = self.request.user
		return MaintenanceTicket.objects.filter(
			unit__building__property__owner=user
		)

	def get_serializer_class(self):
		if self.request.method == "POST":
			return MaintenanceTicketCreateSerializer
		return MaintenanceTicketSerializer

	def perform_create(self, serializer):
		serializer.save(reported_by=self.request.user)


class MaintenanceTicketDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "maintenance.ticket.view"
	queryset = MaintenanceTicket.objects.all()
	serializer_class = MaintenanceTicketSerializer

	def get_object(self):
		return get_object_or_404(MaintenanceTicket, pk=self.kwargs.get("pk"), unit__building__property__owner=self.request.user)


class MaintenanceTicketChangeStatusAPIView(APIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "maintenance.ticket.change_status"

	def post(self, request, pk):
		ticket = get_object_or_404(MaintenanceTicket, pk=pk, unit__building__property__owner=request.user)
		status_value = request.data.get("status")
		if status_value not in dict(MaintenanceTicket.STATUS_CHOICES):
			return Response({"detail": "Invalid status"}, status=status.HTTP_400_BAD_REQUEST)
		ticket.status = status_value
		ticket.save()
		return Response(MaintenanceTicketSerializer(ticket).data)


class MaintenanceTicketAssignAPIView(APIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "maintenance.ticket.assign"

	def post(self, request, pk):
		ticket = get_object_or_404(MaintenanceTicket, pk=pk, unit__building__property__owner=request.user)
		assigned_to_id = request.data.get("assigned_to")
		assigned_to = get_object_or_404(request.user.__class__, pk=assigned_to_id)
		assignment = MaintenanceAssignment.objects.create(ticket=ticket, assigned_to=assigned_to, assigned_by=request.user)
		return Response(MaintenanceAssignmentSerializer(assignment).data, status=status.HTTP_201_CREATED)


class MaintenanceLogListCreateAPIView(generics.ListCreateAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "maintenance.log.view"

	serializer_class = MaintenanceLogSerializer

	def get_queryset(self):
		ticket_pk = self.kwargs.get("pk")
		ticket = get_object_or_404(MaintenanceTicket, pk=ticket_pk, unit__building__property__owner=self.request.user)
		return MaintenanceLog.objects.filter(ticket=ticket)

	def perform_create(self, serializer):
		ticket_pk = self.kwargs.get("pk")
		ticket = get_object_or_404(MaintenanceTicket, pk=ticket_pk, unit__building__property__owner=self.request.user)
		serializer.save(ticket=ticket, user=self.request.user)

