from rest_framework import serializers

from deposits.models import DepositDeduction, DepositSettlement
from deposits.services import DEPOSIT_STATES
from inspections.models import InspectionItem
from payments.models import DEPOSIT_METHOD, PaymentMethod

MONEY = {"max_digits": 14, "decimal_places": 2}


class DepositDeductionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DepositDeduction
        fields = ["kind", "label", "amount"]
        extra_kwargs = {"amount": {"min_value": 1}}


class DepositSettlementSerializer(serializers.ModelSerializer):
    number = serializers.CharField(read_only=True)
    method_label = serializers.CharField(source="method.label", read_only=True, default="")
    deductions = DepositDeductionSerializer(many=True, read_only=True)
    retained_unpaid = serializers.DecimalField(source="rent_payment.amount_paid", read_only=True, default="0.00", **MONEY)

    class Meta:
        model = DepositSettlement
        fields = [
            "id", "number", "lease", "held_amount", "retained_unpaid", "deductions", "refund_amount", "settled_on",
            "method_label", "reference", "note", "cancelled_at", "cancel_reason",
        ]
        read_only_fields = fields


class DepositFaultSerializer(serializers.Serializer):
    room = serializers.CharField()
    label = serializers.CharField()
    condition = serializers.ChoiceField(choices=InspectionItem.CONDITIONS)
    note = serializers.CharField()


class DepositSummarySerializer(serializers.Serializer):
    lease = serializers.IntegerField()
    state = serializers.ChoiceField(choices=DEPOSIT_STATES)
    held = serializers.DecimalField(**MONEY)
    declared = serializers.BooleanField(help_text="Caution inscrite au bail, sans encaissement dans Dahoo : montant à confirmer")
    unpaid = serializers.DecimalField(**MONEY)
    unpaid_count = serializers.IntegerField()
    faults = DepositFaultSerializer(many=True)
    exit_inspection = serializers.CharField(help_text="Statut de l'état des lieux de sortie, vide s'il n'existe pas")
    settlement = DepositSettlementSerializer(allow_null=True)


class SettleDepositSerializer(serializers.Serializer):
    held = serializers.DecimalField(min_value=0, required=False, allow_null=True, default=None, max_digits=12, decimal_places=2)
    retain_unpaid = serializers.DecimalField(min_value=0, required=False, default=0, max_digits=12, decimal_places=2)
    deductions = DepositDeductionSerializer(many=True, required=False, default=list)
    method = serializers.PrimaryKeyRelatedField(queryset=PaymentMethod.objects.exclude(code=DEPOSIT_METHOD), required=False, allow_null=True, default=None)
    reference = serializers.CharField(required=False, allow_blank=True, default="", max_length=100)
    note = serializers.CharField(required=False, allow_blank=True, default="", max_length=300)
    settled_on = serializers.DateField(required=False, allow_null=True, default=None)


class CancelSettlementSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=200)


class DepositRowSerializer(serializers.Serializer):
    lease = serializers.IntegerField()
    state = serializers.ChoiceField(choices=DEPOSIT_STATES)
    tenant_name = serializers.CharField()
    unit_reference = serializers.CharField()
    property_name = serializers.CharField()
    held = serializers.DecimalField(**MONEY)
    expected = serializers.DecimalField(**MONEY)
    declared = serializers.BooleanField()
    ended_on = serializers.DateField(allow_null=True)
    refunded = serializers.DecimalField(allow_null=True, **MONEY)
    settled_on = serializers.DateField(allow_null=True)


class DepositBoardSerializer(serializers.Serializer):
    held = serializers.DecimalField(**MONEY)
    held_count = serializers.IntegerField()
    to_return = serializers.DecimalField(**MONEY)
    to_return_count = serializers.IntegerField()
    rows = DepositRowSerializer(many=True)
