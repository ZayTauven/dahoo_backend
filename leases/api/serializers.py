from django.contrib.auth import get_user_model
from rest_framework import serializers

from leases.models import LeaseContract
from organizations.scoping import OrganizationScopedRelatedField
from properties.models import Unit

User = get_user_model()


class LeaseContractSerializer(serializers.ModelSerializer):
    unit = OrganizationScopedRelatedField(
        queryset=Unit.objects.all(), organization_lookup="building__property__organization"
    )
    tenant = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())

    class Meta:
        model = LeaseContract
        fields = [
            "id",
            "status",
            "unit",
            "tenant",
            "start_date",
            "end_date",
            "rent_amount",
            "charges_amount",
            "deposit_amount",
            "payment_frequency",
            "created_by",
            "created_at",
            "signed_at",
        ]
        read_only_fields = ["status", "created_by", "created_at", "signed_at"]
        extra_kwargs = {
            "rent_amount": {"min_value": 0},
            "charges_amount": {"min_value": 0},
            "deposit_amount": {"min_value": 0},
        }

    def validate(self, attrs):
        start, end = attrs.get("start_date"), attrs.get("end_date")
        if start and end and end <= start:
            raise serializers.ValidationError({"end_date": "La date de fin doit être postérieure au début."})
        return attrs
