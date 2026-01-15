from rest_framework import serializers
from field_ops.models import GuardianProfile, FieldEvent, VisitEvent, DeliveryEvent


class GuardianProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = GuardianProfile
        fields = ["id", "user", "shift_start", "shift_end", "active", "buildings"]


class FieldEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = FieldEvent
        fields = ["id", "building", "unit", "recorded_by", "event_type", "description", "occurred_at", "created_at"]


class FieldEventCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = FieldEvent
        fields = ["building", "unit", "event_type", "description", "occurred_at"]


class VisitEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = VisitEvent
        fields = ["id", "field_event", "visitor_name", "purpose", "authorized_by"]


class DeliveryEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryEvent
        fields = ["id", "field_event", "company", "package_count", "recipient"]
