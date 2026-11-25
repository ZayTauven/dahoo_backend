from decimal import Decimal

from django.db import transaction
from django.db.models import DecimalField, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django_filters import rest_framework as filters
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from access.permissions import IsStaffOrReadOnly
from dahoo.exceptions import Conflict
from documents.http import parse_month, pdf_response
from documents.receipts import (
	payment_receipt,
	rent_receipt,
	rent_schedules,
	share_payment_receipt,
	share_rent_receipt,
)
from leases.models import LeaseContract
from mailing.agency import email_payment_documents, email_rent_overdue, email_rent_receipt
from leases.tenants import tenant_name_subquery
from organizations.scoping import OrganizationScopedMixin
from payments.models import DEPOSIT_METHOD, Payment, PaymentAllocation, PaymentMethod, PaymentSchedule, RentReminder
from payments.reminders import record_reminder, reminder_for
from payments.rent_roll import build_rent_roll
from payments.services import allocate_payment, cancel_payment, collect_rent, email_documents

from .serializers import (
	AllocationRequestSerializer,
	AllocationResultSerializer,
	CancelSerializer,
	CollectRentSerializer,
	CollectResultSerializer,
	PaymentAllocationSerializer,
	PaymentCreateSerializer,
	PaymentMethodSerializer,
	PaymentScheduleSerializer,
	PaymentSerializer,
	ReminderRequestSerializer,
	ReminderSerializer,
	RentReminderSerializer,
	RentRollSerializer,
	ShareLinkSerializer,
)


# Moyens de paiement : référentiel commun (Wave, Orange Money...), modifiable par le staff Dahoo.
class PaymentMethodListCreateAPIView(generics.ListCreateAPIView):
	permission_classes = [IsStaffOrReadOnly]
	queryset = PaymentMethod.objects.exclude(code=DEPOSIT_METHOD).order_by("label")
	serializer_class = PaymentMethodSerializer
	pagination_class = None


class PaymentMethodDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
	permission_classes = [IsStaffOrReadOnly]
	queryset = PaymentMethod.objects.all()
	serializer_class = PaymentMethodSerializer


def schedules_with_labels():
	"""Échéances avec de quoi construire `contract_label` sans requête par ligne."""
	paid = (
		PaymentAllocation.objects.filter(schedule=OuterRef("pk"))
		.values("schedule")
		.annotate(total=Sum("allocated_amount"))
		.values("total")
	)
	return PaymentSchedule.objects.select_related(
		"lease_contract__unit", "lease_contract__tenant", "sale_contract__unit", "sale_contract__buyer"
	).annotate(
		tenant_profile_name=tenant_name_subquery("lease_contract__tenant"),
		amount_paid=Coalesce(Subquery(paid, output_field=DecimalField(max_digits=12, decimal_places=2)), Value(Decimal("0"))),
	)


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

	def perform_destroy(self, instance):
		if instance.allocations.exists():
			raise Conflict("Suppression impossible : un paiement est affecté à cette échéance. Annulez d'abord le paiement.")
		instance.delete()


def payments_with_labels():
	"""Paiements avec allocations et nom du payeur (fiche locataire de l'organisation)."""
	return (
		Payment.objects.select_related("payer", "payment_method")
		.prefetch_related("allocations", "allocations__schedule__lease_contract__unit")
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
		email_documents(payment)
		data = PaymentSerializer(payment, context=self.get_serializer_context()).data
		return Response(data, status=status.HTTP_201_CREATED)


class PaymentDetailAPIView(OrganizationScopedMixin, generics.RetrieveAPIView):
	capability_resource = "payment"
	queryset = payments_with_labels()
	serializer_class = PaymentSerializer


class PaymentCancelAPIView(OrganizationScopedMixin, APIView):
	"""Annule un paiement saisi par erreur : il reste visible, ses échéances redeviennent dues."""

	required_capability = "payment.cancel"

	@extend_schema(request=CancelSerializer, responses=PaymentSerializer)
	def post(self, request, pk):
		payment = get_object_or_404(Payment, pk=pk, organization=self.organization)
		serializer = CancelSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		payment = cancel_payment(payment, user=request.user, reason=serializer.validated_data["reason"])
		return Response(PaymentSerializer(payment, context={"request": request}).data)


class CollectRentAPIView(OrganizationScopedMixin, APIView):
	"""Encaisser un loyer en un geste : paiement enregistré et affecté aux échéances les plus anciennes."""

	required_capability = "payment.create"

	@extend_schema(request=CollectRentSerializer, responses={201: CollectResultSerializer})
	def post(self, request):
		serializer = CollectRentSerializer(data=request.data, context={"request": request})
		serializer.is_valid(raise_exception=True)
		payment = collect_rent(recorded_by=request.user, **serializer.validated_data)
		payment = payments_with_labels().get(pk=payment.pk)
		settled = [
			allocation.schedule_id
			for allocation in payment.allocations.all()
			if allocation.schedule.is_paid and allocation.schedule.schedule_type in ("RENT", "CHARGE")
		]
		data = CollectResultSerializer({"payment": payment, "receipts": settled}, context={"request": request}).data
		return Response(data, status=status.HTTP_201_CREATED)


class RentRollAPIView(OrganizationScopedMixin, APIView):
	"""Loyers d'un mois (courant par défaut) : une ligne par bail, avec le reste dû et les arriérés."""

	required_capability = "payment.schedule.view"

	@extend_schema(
		parameters=[OpenApiParameter("month", OpenApiTypes.STR, description="Mois « AAAA-MM », le mois courant par défaut.")],
		responses=RentRollSerializer,
	)
	def get(self, request):
		month = parse_month(request.query_params.get("month"))
		return Response(RentRollSerializer(build_rent_roll(self.organization, month=month)).data)


class RentReminderListCreateAPIView(OrganizationScopedMixin, generics.ListAPIView):
	"""Relances d'un bail (`?lease=`) ; POST trace la relance et renvoie le message et le lien WhatsApp."""

	capability_resource = "payment.reminder"
	queryset = RentReminder.objects.select_related("sent_by")
	serializer_class = RentReminderSerializer
	filterset_fields = ["lease"]

	@extend_schema(request=ReminderRequestSerializer, responses={201: ReminderSerializer})
	def post(self, request):
		serializer = ReminderRequestSerializer(data=request.data, context={"request": request})
		serializer.is_valid(raise_exception=True)
		lease, channel = serializer.validated_data["lease"], serializer.validated_data["channel"]
		if channel == "EMAIL":
			# Envoyé avant d'être tracé : sans adresse utilisable, rien n'est noté.
			email_rent_overdue(lease, reminder_for(lease))
		reminder = record_reminder(lease, user=request.user, channel=channel)
		return Response(ReminderSerializer(reminder).data, status=status.HTTP_201_CREATED)


class ReminderPreviewAPIView(OrganizationScopedMixin, APIView):
	required_capability = "payment.reminder.view"

	@extend_schema(responses=ReminderSerializer)
	def get(self, request, pk):
		lease = get_object_or_404(LeaseContract.objects.select_related("organization", "unit__building__property"), pk=pk, organization=self.organization)
		return Response(ReminderSerializer(reminder_for(lease)).data)


class RentReceiptAPIView(OrganizationScopedMixin, APIView):
	"""Quittance PDF d'une échéance de loyer soldée."""

	required_capability = "payment.view"

	@extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
	def get(self, request, pk):
		schedule = get_object_or_404(rent_schedules(), pk=pk, organization=self.organization)
		return pdf_response(rent_receipt(schedule))


class RentReceiptShareAPIView(OrganizationScopedMixin, APIView):
	required_capability = "payment.view"

	@extend_schema(responses=ShareLinkSerializer)
	def get(self, request, pk):
		schedule = get_object_or_404(rent_schedules(), pk=pk, organization=self.organization)
		return Response(ShareLinkSerializer(share_rent_receipt(schedule)).data)


class RentReceiptEmailAPIView(OrganizationScopedMixin, APIView):
	"""Envoie la quittance par e-mail au locataire."""

	required_capability = "payment.create"
	throttle_scope = "email_send"

	@extend_schema(request=None, responses={204: None})
	def post(self, request, pk):
		schedule = get_object_or_404(rent_schedules(), pk=pk, organization=self.organization)
		email_rent_receipt(schedule)
		return Response(status=status.HTTP_204_NO_CONTENT)


class PaymentReceiptEmailAPIView(OrganizationScopedMixin, APIView):
	"""Envoie par e-mail la quittance de chaque loyer soldé par ce paiement, ou son reçu."""

	required_capability = "payment.create"
	throttle_scope = "email_send"

	@extend_schema(request=None, responses={204: None})
	def post(self, request, pk):
		payment = get_object_or_404(Payment.objects.select_related("organization", "payer", "payment_method"), pk=pk, organization=self.organization)
		email_payment_documents(payment)
		return Response(status=status.HTTP_204_NO_CONTENT)


class PaymentReceiptAPIView(OrganizationScopedMixin, APIView):
	"""Reçu PDF d'un paiement."""

	required_capability = "payment.view"

	@extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
	def get(self, request, pk):
		payment = get_object_or_404(Payment.objects.select_related("organization", "payer", "payment_method"), pk=pk, organization=self.organization)
		return pdf_response(payment_receipt(payment))


class PaymentReceiptShareAPIView(OrganizationScopedMixin, APIView):
	required_capability = "payment.view"

	@extend_schema(responses=ShareLinkSerializer)
	def get(self, request, pk):
		payment = get_object_or_404(Payment.objects.select_related("organization", "payer"), pk=pk, organization=self.organization)
		return Response(ShareLinkSerializer(share_payment_receipt(payment)).data)


class PaymentAllocateAPIView(OrganizationScopedMixin, APIView):
	required_capability = "payment.allocate"

	@extend_schema(request=AllocationRequestSerializer, responses={201: AllocationResultSerializer})
	def post(self, request, pk):
		payment = get_object_or_404(Payment, pk=pk, organization=self.organization)
		serializer = AllocationRequestSerializer(data=request.data, context={"request": request})
		serializer.is_valid(raise_exception=True)
		created = allocate_payment(payment, serializer.validated_data["allocations"])
		return Response(
			{"allocations": PaymentAllocationSerializer(created, many=True).data},
			status=status.HTTP_201_CREATED,
		)
