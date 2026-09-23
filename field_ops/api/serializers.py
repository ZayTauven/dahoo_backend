from django.contrib.auth import get_user_model
from rest_framework import serializers

from field_ops.models import DeliveryEvent, FieldEvent, GuardianProfile, VisitEvent
from organizations.scoping import OrganizationScopedRelatedField
from properties.models import Building, Unit

User = get_user_model()


class GuardianProfileSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())
    buildings = OrganizationScopedRelatedField(
        queryset=Building.objects.all(), organization_lookup="property__organization", many=True
    )

    class Meta:
        model = GuardianProfile
        fields = ["id", "user", "shift_start", "shift_end", "active", "buildings"]


class FieldEventSerializer(serializers.ModelSerializer):
    building = OrganizationScopedRelatedField(
        queryset=Building.objects.all(), organization_lookup="property__organization"
    )
    unit = OrganizationScopedRelatedField(
        queryset=Unit.objects.all(),
        organization_lookup="building__property__organization",
        required=False,
        allow_null=True,
    )

    class Meta:
        model = FieldEvent
        fields = ["id", "building", "unit", "recorded_by", "event_type", "description", "occurred_at", "created_at"]
        read_only_fields = ["recorded_by", "created_at"]

    def validate(self, attrs):
        unit, building = attrs.get("unit"), attrs.get("building")
        if unit and building and unit.building_id != building.id:
            raise serializers.ValidationError({"unit": "Ce lot n'appartient pas au bâtiment indiqué."})
        return attrs


class VisitEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = VisitEvent
        fields = ["id", "field_event", "visitor_name", "purpose", "authorized_by"]


class DeliveryEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryEvent
        fields = ["id", "field_event", "company", "package_count", "recipient"]
