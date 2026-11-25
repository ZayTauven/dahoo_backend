from decimal import Decimal

from rest_framework import serializers

from maintenance.models import MaintenanceTicket
from organizations.scoping import OrganizationScopedRelatedField
from owners.models import Expense, Owner, OwnerPayout
from owners.owners import register_owner
from properties.models import Property, Unit
from users.phone import validate_phone

MIN_AMOUNT = Decimal("0.01")


class OwnerSerializer(serializers.ModelSerializer):
    phone = serializers.CharField(source="user.phone", max_length=20)
    full_name = serializers.CharField(read_only=True)
    properties_count = serializers.IntegerField(read_only=True, default=0)
    units_count = serializers.IntegerField(read_only=True, default=0)
    balance = serializers.SerializerMethodField(help_text="Solde à reverser aujourd'hui")

    class Meta:
        model = Owner
        fields = [
            "id", "phone", "first_name", "last_name", "full_name", "email", "address", "payout_channel",
            "payout_details", "notes", "properties_count", "units_count", "balance", "created_at",
        ]
        read_only_fields = ["created_at"]

    def get_balance(self, owner) -> str:
        row = self.context.get("balances", {}).get(owner.pk)
        return f"{row['balance'] if row else Decimal('0'):.2f}"

    def validate_phone(self, value):
        value = validate_phone(value)
        if self.instance is not None and value != self.instance.user.phone:
            raise serializers.ValidationError("Le téléphone d'un bailleur ne peut pas être modifié.")
        organization = self.context["request"].organization
        if self.instance is None and Owner.objects.filter(organization=organization, user__phone=value).exists():
            raise serializers.ValidationError("Ce numéro est déjà enregistré comme bailleur.")
        return value

    def create(self, validated_data):
        phone = validated_data.pop("user")["phone"]
        return register_owner(self.context["request"].organization, phone=phone, **validated_data)

    def update(self, instance, validated_data):
        validated_data.pop("user", None)
        return super().update(instance, validated_data)


class ExpenseSerializer(serializers.ModelSerializer):
    property = OrganizationScopedRelatedField(queryset=Property.objects.all())
    unit = OrganizationScopedRelatedField(
        queryset=Unit.objects.select_related("building"),
        organization_lookup="building__property__organization", required=False, allow_null=True,
    )
    ticket = OrganizationScopedRelatedField(
        queryset=MaintenanceTicket.objects.all(),
        organization_lookup="unit__building__property__organization", required=False, allow_null=True,
    )
    property_name = serializers.CharField(source="property.name", read_only=True)
    unit_reference = serializers.CharField(source="unit.reference", read_only=True, default="")
    category_label = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = Expense
        fields = [
            "id", "property", "property_name", "unit", "unit_reference", "ticket", "category", "category_label",
            "label", "amount", "spent_on", "note", "created_at",
        ]
        read_only_fields = ["created_at"]
        extra_kwargs = {"amount": {"min_value": MIN_AMOUNT}}

    def validate(self, attrs):
        prop = attrs.get("property", getattr(self.instance, "property", None))
        unit = attrs.get("unit", getattr(self.instance, "unit", None))
        if unit and unit.building.property_id != prop.pk:
            raise serializers.ValidationError({"unit": "Ce lot n'appartient pas au bien choisi."})
        return attrs


class OwnerPayoutSerializer(serializers.ModelSerializer):
    owner = OrganizationScopedRelatedField(queryset=Owner.objects.all())
    owner_name = serializers.CharField(source="owner.full_name", read_only=True)
    channel_label = serializers.CharField(source="get_channel_display", read_only=True)

    class Meta:
        model = OwnerPayout
        fields = [
            "id", "owner", "owner_name", "amount", "paid_on", "channel", "channel_label", "reference", "note",
            "cancelled_at", "cancel_reason", "created_at",
        ]
        read_only_fields = ["cancelled_at", "cancel_reason", "created_at"]
        extra_kwargs = {"amount": {"min_value": MIN_AMOUNT}}


class StatementUnitSerializer(serializers.Serializer):
    lease = serializers.IntegerField()
    unit_reference = serializers.CharField()
    property_name = serializers.CharField()
    tenant_name = serializers.CharField()
    expected = serializers.DecimalField(max_digits=14, decimal_places=2)
    collected = serializers.DecimalField(max_digits=14, decimal_places=2)
    commission = serializers.DecimalField(max_digits=14, decimal_places=2)
    unpaid = serializers.DecimalField(max_digits=14, decimal_places=2)


class StatementExpenseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    date = serializers.DateField()
    label = serializers.CharField()
    property_name = serializers.CharField()
    unit_reference = serializers.CharField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)


class StatementPayoutSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    date = serializers.DateField()
    channel = serializers.CharField()
    reference = serializers.CharField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)


class StatementSerializer(serializers.Serializer):
    owner = serializers.IntegerField()
    owner_name = serializers.CharField()
    month = serializers.DateField()
    ends = serializers.DateField()
    opening_balance = serializers.DecimalField(max_digits=14, decimal_places=2)
    expected = serializers.DecimalField(max_digits=14, decimal_places=2)
    collected = serializers.DecimalField(max_digits=14, decimal_places=2)
    commission = serializers.DecimalField(max_digits=14, decimal_places=2)
    unpaid = serializers.DecimalField(max_digits=14, decimal_places=2)
    retentions = serializers.DecimalField(max_digits=14, decimal_places=2, help_text="Retenues sur cautions, reversées sans commission")
    expenses = serializers.DecimalField(max_digits=14, decimal_places=2)
    payouts = serializers.DecimalField(max_digits=14, decimal_places=2)
    net = serializers.DecimalField(max_digits=14, decimal_places=2)
    closing_balance = serializers.DecimalField(max_digits=14, decimal_places=2)
    units = StatementUnitSerializer(many=True)
    retention_lines = StatementExpenseSerializer(many=True)
    expense_lines = StatementExpenseSerializer(many=True)
    payout_lines = StatementPayoutSerializer(many=True)
