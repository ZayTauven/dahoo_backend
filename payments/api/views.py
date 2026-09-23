from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from access.permissions import IsStaffOrReadOnly
from organizations.scoping import OrganizationScopedMixin
from payments.models import Payment, PaymentMethod, PaymentSchedule
from payments.services import allocate_payment

from .serializers import (
	AllocationRequestSerializer,
	PaymentAllocationSerializer,
	PaymentCreateSerializer,
	PaymentMethodSerializer,
	PaymentScheduleSerializer,
	PaymentSerializer,
)


# Moyens de paiement : référentiel commun (Wave, Orange Money...), modifiable par le staff Dahoo.
class PaymentMethodListCreateAPIView(generics.ListCreateAPIView):
	permission_classes = [IsStaffOrReadOnly]
	queryset = PaymentMethod.objects.order_by("label")
	serializer_class = PaymentMethodSerializer
	pagination_class = None


class PaymentMethodDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
	permission_classes = [IsStaffOrReadOnly]
	queryset = PaymentMethod.objects.all()
	serializer_class = PaymentMethodSerializer


class PaymentScheduleListCreateAPIView(OrganizationScopedMixin, generics.ListCreateAPIView):
	capability_resource = "payment.schedule"
	queryset = PaymentSchedule.objects.order_by("due_date")
	serializer_class = PaymentScheduleSerializer

	def perform_create(self, serializer):
		serializer.save(organization=self.organization)


class PaymentScheduleDetailAPIView(OrganizationScopedMixin, generics.RetrieveUpdateDestroyAPIView):
	capability_resource = "payment.schedule"
	queryset = PaymentSchedule.objects.all()
	serializer_class = PaymentScheduleSerializer


class PaymentListCreateAPIView(OrganizationScopedMixin, generics.ListCreateAPIView):
	capability_resource = "payment"
	queryset = Payment.objects.prefetch_related("allocations").order_by("-payment_date")

	def get_serializer_class(self):
		if self.request.method == "POST":
			return PaymentCreateSerializer
		return PaymentSerializer

	@extend_schema(request=PaymentCreateSerializer, responses={201: PaymentSerializer})
	def post(self, request, *args, **kwargs):
		return super().post(request, *args, **kwargs)

	@transaction.atomic
	def create(self, request, *args, **kwargs):
		serializer = self.get_serializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		allocations = serializer.validated_data.pop("allocations", [])
		payment = serializer.save(organization=self.organization, recorded_by=request.user)
		allocate_payment(payment, allocations)
		data = PaymentSerializer(payment, context=self.get_serializer_context()).data
		return Response(data, status=status.HTTP_201_CREATED)


class PaymentDetailAPIView(OrganizationScopedMixin, generics.RetrieveAPIView):
	capability_resource = "payment"
	queryset = Payment.objects.prefetch_related("allocations")
	serializer_class = PaymentSerializer


class PaymentAllocateAPIView(OrganizationScopedMixin, APIView):
	required_capability = "payment.allocate"

	@extend_schema(request=AllocationRequestSerializer, responses={201: PaymentAllocationSerializer(many=True)})
	def post(self, request, pk):
		payment = get_object_or_404(Payment, pk=pk, organization=self.organization)
		serializer = AllocationRequestSerializer(data=request.data, context={"request": request})
		serializer.is_valid(raise_exception=True)
		created = allocate_payment(payment, serializer.validated_data["allocations"])
		return Response(
			{"allocations": PaymentAllocationSerializer(created, many=True).data},
			status=status.HTTP_201_CREATED,
		)
