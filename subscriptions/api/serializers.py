from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from payments.models import DEPOSIT_METHOD, PaymentMethod
from subscriptions.billing import BILLING_STATES
from subscriptions.models import BillingSettings, PlanRequest, Subscription, SubscriptionPayment, SubscriptionPlan

MONEY = {"max_digits": 14, "decimal_places": 2}


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = [
            "id", "name", "description", "audience", "billing_type", "price", "commission_rate",
            "max_properties", "max_units", "max_users", "active",
        ]


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = SubscriptionPlanSerializer(read_only=True)
    state = serializers.ChoiceField(choices=Subscription.STATES, read_only=True)
    days_left = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = Subscription
        fields = ["id", "plan", "status", "state", "price", "start_date", "end_date", "days_left", "created_at"]
        read_only_fields = fields


class SubscriptionPaymentSerializer(serializers.ModelSerializer):
    number = serializers.CharField(read_only=True)
    organization = serializers.IntegerField(source="subscription.organization_id", read_only=True)
    organization_name = serializers.CharField(source="subscription.organization.name", read_only=True)
    method_label = serializers.CharField(source="method.label", read_only=True)

    class Meta:
        model = SubscriptionPayment
        fields = [
            "id", "number", "organization", "organization_name", "subscription", "plan_name", "months", "quantity", "unit_price",
            "credit", "discount", "amount", "period_start", "period_end", "paid_on", "method_label", "reference",
            "cancelled_at", "cancel_reason", "created_at",
        ]
        read_only_fields = fields


class UsageSerializer(serializers.Serializer):
    resource = serializers.ChoiceField(choices=["property", "unit", "member"])
    label = serializers.CharField()
    used = serializers.IntegerField()
    limit = serializers.IntegerField(allow_null=True)


class PlanRequestSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source="plan.name", read_only=True)
    requested_by_name = serializers.SerializerMethodField()
    requested_by_phone = serializers.CharField(source="requested_by.phone", read_only=True)

    class Meta:
        model = PlanRequest
        fields = ["id", "plan", "plan_name", "message", "status", "requested_by_name", "requested_by_phone", "created_at"]
        read_only_fields = ["status", "created_at"]

    def get_requested_by_name(self, request) -> str:
        user = request.requested_by
        return f"{user.first_name} {user.last_name}".strip() or user.phone


class PlanRequestCreateSerializer(serializers.Serializer):
    plan = serializers.PrimaryKeyRelatedField(queryset=SubscriptionPlan.objects.filter(active=True))
    message = serializers.CharField(required=False, allow_blank=True, max_length=600)


class SubscriptionOverviewSerializer(serializers.Serializer):
    """Ce que voit le client : où il en est, ce qu'il consomme, ce qu'il peut choisir."""

    state = serializers.ChoiceField(choices=BILLING_STATES)
    subscription = SubscriptionSerializer(allow_null=True)
    usage = UsageSerializer(many=True)
    request = PlanRequestSerializer(allow_null=True)
    plans = SubscriptionPlanSerializer(many=True)
    payment_instructions = serializers.CharField()


# --- Équipe Dahoo


class PlatformPlanSerializer(serializers.ModelSerializer):
    subscribers = serializers.SerializerMethodField()

    class Meta:
        model = SubscriptionPlan
        fields = SubscriptionPlanSerializer.Meta.fields + ["limits_trial", "subscribers"]
        # L'unicité de limits_trial est garantie à l'enregistrement (l'ancienne offre la perd), pas refusée.
        validators = []
        extra_kwargs = {"limits_trial": {"validators": []}}

    def get_subscribers(self, plan) -> int:
        return sum(subscription.state in ("ACTIVE", "ENDING", "UPCOMING") for subscription in plan.subscriptions.all())

    def validate(self, attrs):
        def value(field):
            return attrs.get(field, getattr(self.instance, field, None))

        if value("billing_type") == "COMMISSION":
            rate = value("commission_rate")
            if rate is None or not 0 < rate <= 100:
                raise serializers.ValidationError({"commission_rate": "Indiquez un taux entre 0 et 100 %."})
            attrs["price"] = None
        else:
            if value("price") is None or value("price") < 0:
                raise serializers.ValidationError({"price": "Indiquez le prix de l'offre."})
            attrs["commission_rate"] = None
        if self.instance and self.instance.subscriptions.exists():
            self._protect_subscribers(attrs)
        return attrs

    def _protect_subscribers(self, attrs):
        """Le prix ne vaut que pour les prochains abonnés ; les limites et le rythme, eux, engagent les abonnés actuels."""
        if "billing_type" in attrs and attrs["billing_type"] != self.instance.billing_type:
            raise serializers.ValidationError({"billing_type": "Des abonnés suivent ce rythme : créez une nouvelle offre."})
        for field in ("max_properties", "max_units", "max_users"):
            if field not in attrs or attrs[field] is None:
                continue
            current = getattr(self.instance, field)
            if current is None or attrs[field] < current:
                raise serializers.ValidationError({field: "Des abonnés ont cette limite : elle peut augmenter, pas baisser. Créez une nouvelle offre."})


class BillingSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = BillingSettings
        fields = ["payment_instructions", "legal_notice"]


class BillingOrganizationSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    kind = serializers.ChoiceField(choices=[("AGENCY", "Agence ou gestionnaire"), ("OWNER", "Propriétaire")])
    phone = serializers.CharField()
    city = serializers.CharField()
    trial_ends_at = serializers.DateTimeField()


class BillingSummarySerializer(serializers.Serializer):
    organization = BillingOrganizationSerializer()
    state = serializers.ChoiceField(choices=BILLING_STATES)
    subscription = SubscriptionSerializer(allow_null=True)
    monthly_value = serializers.DecimalField(**MONEY)
    usage = UsageSerializer(many=True)
    last_payment = SubscriptionPaymentSerializer(allow_null=True)
    request = PlanRequestSerializer(allow_null=True)


class BillingBoardSerializer(serializers.Serializer):
    mrr = serializers.DecimalField(**MONEY)
    collected_month = serializers.DecimalField(**MONEY)
    collected_year = serializers.DecimalField(**MONEY)
    subscribers = serializers.IntegerField()
    to_renew = serializers.IntegerField()
    to_renew_amount = serializers.DecimalField(**MONEY)
    trials = serializers.IntegerField()
    requests = serializers.IntegerField()
    rows = BillingSummarySerializer(many=True)


class QuoteTermsSerializer(serializers.Serializer):
    plan = serializers.PrimaryKeyRelatedField(queryset=SubscriptionPlan.objects.all())
    quantity = serializers.IntegerField(required=False, default=1)
    discount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=0)
    # Commission seulement : ce qui a été réellement encaissé.
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True, default=None)
    paid_on = serializers.DateField(required=False, allow_null=True, default=None)


class QuoteSerializer(serializers.Serializer):
    quantity = serializers.IntegerField()
    unit_price = serializers.DecimalField(**MONEY)
    gross = serializers.DecimalField(**MONEY)
    credit = serializers.DecimalField(**MONEY)
    discount = serializers.DecimalField(**MONEY)
    amount = serializers.DecimalField(**MONEY)
    period_start = serializers.DateField()
    period_end = serializers.DateField()
    free_days = serializers.IntegerField()
    renews = serializers.SerializerMethodField()
    replaces = serializers.CharField(source="replaces.plan.name", allow_null=True, default=None)
    warnings = serializers.ListField(child=serializers.CharField())

    @extend_schema_field(serializers.BooleanField())
    def get_renews(self, quote):
        return quote.renews is not None


class RecordPaymentSerializer(QuoteTermsSerializer):
    method = serializers.SlugRelatedField(slug_field="code", queryset=PaymentMethod.objects.exclude(code=DEPOSIT_METHOD))
    reference = serializers.CharField(required=False, allow_blank=True, default="", max_length=100)
    note = serializers.CharField(required=False, allow_blank=True, default="", max_length=200)


class CancelSubscriptionPaymentSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=200)


class BillingReminderSerializer(serializers.Serializer):
    message = serializers.CharField()
    phone = serializers.CharField(allow_blank=True)
    whatsapp_url = serializers.CharField(allow_blank=True)
