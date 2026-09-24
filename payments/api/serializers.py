from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from leases.models import LeaseContract, SaleContract
from leases.tenants import person_name
from organizations.scoping import OrganizationScopedRelatedField
from payments.models import Payment, PaymentAllocation, PaymentMethod, PaymentSchedule

User = get_user_model()

MIN_AMOUNT = Decimal("0.01")


class PaymentMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentMethod
        fields = ["id", "code", "label"]


class PaymentScheduleSerializer(serializers.ModelSerializer):
    lease_contract = OrganizationScopedRelatedField(
        queryset=LeaseContract.objects.all(), required=False, allow_null=True
    )
    sale_contract = OrganizationScopedRelatedField(
        queryset=SaleContract.objects.all(), required=False, allow_null=True
    )
    # « Bail n°12 · Ibrahima Sarr · A101 » ou « Vente n°3 · ... »
    contract_label = serializers.SerializerMethodField()
    # Montant déjà affecté par des paiements et reste dû (annotés par schedules_with_labels()).
    amount_paid = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True, default=0)
    remaining_amount = serializers.SerializerMethodField()

    class Meta:
        model = PaymentSchedule
        fields = [
            "id", "lease_contract", "sale_contract", "contract_label", "schedule_type",
            "due_date", "amount_due", "amount_paid", "remaining_amount", "is_paid", "created_at",
        ]
        read_only_fields = ["is_paid", "created_at"]
        extra_kwargs = {"amount_due": {"min_value": MIN_AMOUNT}}

    @extend_schema_field(OpenApiTypes.DECIMAL)
    def get_remaining_amount(self, schedule):
        paid = getattr(schedule, "amount_paid", None) or Decimal("0")
        return f"{max(schedule.amount_due - paid, Decimal('0')):.2f}"

    @extend_schema_field(OpenApiTypes.STR)
    def get_contract_label(self, schedule):
        if schedule.lease_contract_id:
            lease = schedule.lease_contract
            name = person_name(schedule, "tenant_profile_name", lease.tenant, schedule.organization_id)
            return f"Bail n°{lease.id} · {name} · {lease.unit.reference}"
        sale = schedule.sale_contract
        name = f"{sale.buyer.first_name} {sale.buyer.last_name}".strip()
        return f"Vente n°{sale.id} · {name} · {sale.unit.reference}"

    def update(self, instance, validated_data):
        # Le contrat peut changer : le nom annoté du locataire ne serait plus à jour.
        vars(instance).pop("tenant_profile_name", None)
        return super().update(instance, validated_data)

    def validate(self, attrs):
        lease = attrs.get("lease_contract", getattr(self.instance, "lease_contract", None))
        sale = attrs.get("sale_contract", getattr(self.instance, "sale_contract", None))
        if bool(lease) == bool(sale):
            raise serializers.ValidationError("Une échéance est liée soit à un bail, soit à une vente (un seul contrat).")
        return attrs


class PaymentAllocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentAllocation
        fields = ["id", "payment", "schedule", "allocated_amount", "created_at"]


class AllocationInputSerializer(serializers.Serializer):
    schedule = OrganizationScopedRelatedField(queryset=PaymentSchedule.objects.all())
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=MIN_AMOUNT)


class AllocationResultSerializer(serializers.Serializer):
    allocations = PaymentAllocationSerializer(many=True)


class AllocationRequestSerializer(serializers.Serializer):
    allocations = AllocationInputSerializer(many=True, allow_empty=False)


class PayerField(serializers.PrimaryKeyRelatedField):
    """Le payeur doit être locataire ou acquéreur d'un contrat de l'organisation."""

    def get_queryset(self):
        organization = getattr(self.context.get("request"), "organization", None)
        if organization is None:
            return User.objects.none()
        return User.objects.filter(
            Q(lease_contracts__organization=organization) | Q(purchase_contracts__organization=organization)
        ).distinct()


class PaymentSerializer(serializers.ModelSerializer):
    payer = PayerField()
    payer_name = serializers.SerializerMethodField()
    allocations = PaymentAllocationSerializer(many=True, read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id", "payer", "payer_name", "amount_paid", "payment_method", "payment_date",
            "reference", "note", "recorded_by", "created_at", "allocations",
        ]
        read_only_fields = ["recorded_by", "created_at"]
        extra_kwargs = {"amount_paid": {"min_value": MIN_AMOUNT}, "payment_date": {"required": False}}

    def validate_payment_date(self, value):
        if value and value > timezone.now():
            raise serializers.ValidationError("La date du paiement ne peut pas être dans le futur.")
        return value

    @extend_schema_field(OpenApiTypes.STR)
    def get_payer_name(self, payment):
        return person_name(payment, "payer_profile_name", payment.payer, payment.organization_id)


class PaymentCreateSerializer(PaymentSerializer):
    allocations = AllocationInputSerializer(many=True, required=False, write_only=True)
