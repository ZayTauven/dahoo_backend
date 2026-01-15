from rest_framework import serializers
from subscriptions.models import SubscriptionPlan, Subscription, SubscriptionPayment


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = ["id", "name", "billing_type", "price", "commission_rate", "max_properties", "max_units", "max_users", "active"]


class SubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscription
        fields = ["id", "owner", "plan", "status", "start_date", "end_date", "created_at"]
        read_only_fields = ["owner", "created_at"]


class SubscriptionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscription
        fields = ["plan", "start_date", "end_date"]


class SubscriptionPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPayment
        fields = ["id", "subscription", "payment"]
