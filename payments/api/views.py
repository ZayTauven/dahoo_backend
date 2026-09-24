from django.db import transaction
from django.shortcuts import get_object_or_404
from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from access.permissions import IsStaffOrReadOnly
from leases.tenants import tenant_name_subquery
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


def schedules_with_labels():
	"""Échéances avec de quoi construire `contract_label` sans requête par ligne."""
	return PaymentSchedule.objects.select_related(
		"lease_contract__unit", "lease_contract__tenant", "sale_contract__unit", "sale_contract__buyer"
	).annotate(tenant_profile_name=tenant_name_subquery("lease_contract__tenant"))


class PaymentScheduleFilter(filters.FilterSet):
	lease_contract = filters.NumberFilter(field_name="lease_contract_id")
	sale_contract = filters.NumberFilter(field_name="sale_contract_id")
	due_date_after = filters.DateFilter(field_name="due_date", lookup_expr="gte")
	due_date_before = filters.DateFilter(field_name="due_date", lookup_expr="lte")

	class Meta:
		model = PaymentSchedule
		fields = ["is_paid", "schedule_type", "lease_contract", "sale_contract", "due_date_after", "due_date_before"]


class PaymentScheduleListCreateAPIView(OrganizationScopedMixin, generics.ListCreateAPIView):
	capability_resource = "payment.schedule"
	queryset = schedules_with_labels().order_by("due_date", "id")
	serializer_class = PaymentScheduleSerializer
	filterset_class = PaymentScheduleFilter
	ordering_fields = ["due_date", "amount_due", "created_at"]

	def perform_create(self, serializer):
		serializer.save(organization=self.organization)


class PaymentScheduleDetailAPIView(OrganizationScopedMixin, generics.RetrieveUpdateDestroyAPIView):
	capability_resource = "payment.schedule"
	queryset = schedules_with_labels()
	serializer_class = PaymentScheduleSerializer


def payments_with_labels():
	"""Paiements avec allocations et nom du payeur (fiche locataire de l'organisation)."""
	return (
		Payment.objects.select_related("payer")
		.prefetch_related("allocations")
		.annotate(payer_profile_name=tenant_name_subquery("payer"))
	)


class PaymentFilter(filters.FilterSet):
	payer = filters.NumberFilter(field_name="payer_id")
	payment_method = filters.NumberFilter(field_name="payment_method_id")
	payment_date_after = filters.DateFilter(field_name="payment_date", lookup_expr="date__gte")
	payment_date_before = filters.DateFilter(field_name="payment_date", lookup_expr="date__lte")

	class Meta:
		model = Payment
		fields = ["payer", "payment_method", "payment_date_after", "payment_date_before"]


class PaymentListCreateAPIView(OrganizationScopedMixin, generics.ListCreateAPIView):
	capability_resource = "payment"
	queryset = payments_with_labels().order_by("-payment_date")
	filterset_class = PaymentFilter
	search_fields = ["reference", "note"]
	ordering_fields = ["payment_date", "amount_paid"]

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
	queryset = payments_with_labels()
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
