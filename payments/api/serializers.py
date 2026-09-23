from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import serializers

from leases.models import LeaseContract, SaleContract
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

    class Meta:
        model = PaymentSchedule
        fields = ["id", "lease_contract", "sale_contract", "schedule_type", "due_date", "amount_due", "is_paid", "created_at"]
        read_only_fields = ["is_paid", "created_at"]
        extra_kwargs = {"amount_due": {"min_value": MIN_AMOUNT}}

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
    allocations = PaymentAllocationSerializer(many=True, read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id", "payer", "amount_paid", "payment_method", "payment_date",
            "reference", "note", "recorded_by", "created_at", "allocations",
        ]
        read_only_fields = ["payment_date", "recorded_by", "created_at"]
        extra_kwargs = {"amount_paid": {"min_value": MIN_AMOUNT}}


class PaymentCreateSerializer(PaymentSerializer):
    allocations = AllocationInputSerializer(many=True, required=False, write_only=True)
