from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from leases.models import LeaseContract, SaleContract
from leases.tenants import person_name
from notifications.services import money
from organizations.scoping import OrganizationScopedRelatedField
from payments.models import DEPOSIT_METHOD, Payment, PaymentAllocation, PaymentMethod, PaymentSchedule, RentReminder
from payments.rent_roll import RENT_STATUSES
from payments.services import allocated_total, refresh_paid

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
        # « Soldée » dépend du montant dû : recalculé avec lui.
        return refresh_paid(super().update(instance, validated_data))

    def validate(self, attrs):
        lease = attrs.get("lease_contract", getattr(self.instance, "lease_contract", None))
        sale = attrs.get("sale_contract", getattr(self.instance, "sale_contract", None))
        if bool(lease) == bool(sale):
            raise serializers.ValidationError("Une échéance est liée soit à un bail, soit à une vente (un seul contrat).")
        self.check_allocated(attrs)
        return attrs

    def check_allocated(self, attrs):
        """Une échéance déjà réglée, même en partie, garde son contrat et couvre ce qui a été payé."""
        if self.instance is None:
            return
        paid = allocated_total(self.instance.allocations.all())
        if not paid:
            return
        for field in ("lease_contract", "sale_contract", "schedule_type"):
            if field in attrs and attrs[field] != getattr(self.instance, field):
                raise serializers.ValidationError({field: "Un paiement est déjà affecté à cette échéance."})
        if attrs.get("amount_due", paid) < paid:
            raise serializers.ValidationError({"amount_due": f"Déjà réglé : {money(paid)}. Le montant ne peut pas être inférieur."})


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
    payment_method_label = serializers.CharField(source="payment_method.label", read_only=True)
    units = serializers.SerializerMethodField(help_text="Lots des échéances réglées par ce paiement")
    allocations = PaymentAllocationSerializer(many=True, read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id", "payer", "payer_name", "units", "amount_paid", "payment_method", "payment_method_label", "payment_date",
            "reference", "note", "recorded_by", "created_at", "cancelled_at", "cancel_reason", "allocations",
        ]
        read_only_fields = ["recorded_by", "created_at", "cancelled_at", "cancel_reason"]
        extra_kwargs = {"amount_paid": {"min_value": MIN_AMOUNT}, "payment_date": {"required": False}}

    def validate_payment_method(self, method):
        if method.code == DEPOSIT_METHOD:
            raise serializers.ValidationError("Une retenue se saisit dans le décompte de caution.")
        return method

    def validate_payment_date(self, value):
        if value and value > timezone.now():
            raise serializers.ValidationError("La date du paiement ne peut pas être dans le futur.")
        return value

    @extend_schema_field(OpenApiTypes.STR)
    def get_payer_name(self, payment):
        return person_name(payment, "payer_profile_name", payment.payer, payment.organization_id)

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_units(self, payment):
        units = []
        for allocation in payment.allocations.all():
            lease = allocation.schedule.lease_contract
            if lease and lease.unit.reference not in units:
                units.append(lease.unit.reference)
        return units


class CollectRentSerializer(serializers.Serializer):
    """Encaissement rapide d'un loyer : le serveur solde les échéances du bail, les plus anciennes d'abord."""

    lease = OrganizationScopedRelatedField(queryset=LeaseContract.objects.select_related("tenant"))
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=MIN_AMOUNT)
    payment_method = serializers.PrimaryKeyRelatedField(queryset=PaymentMethod.objects.exclude(code=DEPOSIT_METHOD))
    payment_date = serializers.DateTimeField(required=False)
    reference = serializers.CharField(max_length=100, required=False, allow_blank=True)
    note = serializers.CharField(required=False, allow_blank=True)

    def validate_payment_date(self, value):
        if value > timezone.now():
            raise serializers.ValidationError("La date du paiement ne peut pas être dans le futur.")
        return value

    def validate_lease(self, lease):
        if lease.status in ("DRAFT", "CANCELLED"):
            raise serializers.ValidationError("Ce bail n'est pas en cours.")
        return lease


class CancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=200)


class ShareLinkSerializer(serializers.Serializer):
    url = serializers.CharField(help_text="Lien public signé du document PDF")
    message = serializers.CharField()
    whatsapp_url = serializers.CharField()


class CollectResultSerializer(serializers.Serializer):
    payment = PaymentSerializer()
    receipts = serializers.ListField(
        child=serializers.IntegerField(), help_text="Échéances soldées par ce paiement (quittance disponible)"
    )


class ReminderRequestSerializer(serializers.Serializer):
    lease = OrganizationScopedRelatedField(queryset=LeaseContract.objects.all())
    channel = serializers.ChoiceField(choices=RentReminder.CHANNELS, default="WHATSAPP")


class ReminderSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    count = serializers.IntegerField()
    message = serializers.CharField()
    whatsapp_url = serializers.CharField()


class RentReminderSerializer(serializers.ModelSerializer):
    sent_by_name = serializers.SerializerMethodField()

    class Meta:
        model = RentReminder
        fields = ["id", "lease", "channel", "amount", "message", "sent_by_name", "created_at"]

    @extend_schema_field(OpenApiTypes.STR)
    def get_sent_by_name(self, reminder):
        return f"{reminder.sent_by.first_name} {reminder.sent_by.last_name}".strip() if reminder.sent_by else "Envoi automatique"


class RentRollRowSerializer(serializers.Serializer):
    lease = serializers.IntegerField()
    lease_status = serializers.ChoiceField(choices=LeaseContract.STATUS_CHOICES)
    tenant = serializers.IntegerField()
    tenant_name = serializers.CharField()
    tenant_phone = serializers.CharField()
    tenant_email = serializers.CharField(allow_blank=True, help_text="Adresse utilisable, vide sinon")
    unit = serializers.IntegerField()
    unit_reference = serializers.CharField()
    property = serializers.IntegerField()
    property_name = serializers.CharField()
    schedule = serializers.IntegerField(allow_null=True, help_text="Première échéance du mois")
    due_date = serializers.DateField(allow_null=True)
    due = serializers.DecimalField(max_digits=14, decimal_places=2, help_text="Dû au titre du mois")
    paid = serializers.DecimalField(max_digits=14, decimal_places=2)
    remaining = serializers.DecimalField(max_digits=14, decimal_places=2)
    arrears = serializers.DecimalField(max_digits=14, decimal_places=2, help_text="Impayés des mois précédents")
    overdue = serializers.DecimalField(max_digits=14, decimal_places=2, help_text="Tout ce qui est échu et impayé")
    total_due = serializers.DecimalField(max_digits=14, decimal_places=2, help_text="Reste du mois + arriérés")
    oldest_unpaid = serializers.DateField(allow_null=True)
    days_late = serializers.IntegerField()
    status = serializers.ChoiceField(choices=RENT_STATUSES)
    last_reminder_at = serializers.DateTimeField(allow_null=True)


class RentRollCountsSerializer(serializers.Serializer):
    PAID = serializers.IntegerField()
    PARTIAL = serializers.IntegerField()
    LATE = serializers.IntegerField()
    DUE = serializers.IntegerField()
    NONE = serializers.IntegerField()


class RentRollSerializer(serializers.Serializer):
    month = serializers.DateField()
    expected = serializers.DecimalField(max_digits=14, decimal_places=2)
    collected = serializers.DecimalField(max_digits=14, decimal_places=2)
    remaining = serializers.DecimalField(max_digits=14, decimal_places=2)
    overdue = serializers.DecimalField(max_digits=14, decimal_places=2)
    counts = RentRollCountsSerializer()
    rows = RentRollRowSerializer(many=True)


class PaymentCreateSerializer(PaymentSerializer):
    allocations = AllocationInputSerializer(many=True, required=False, write_only=True)
