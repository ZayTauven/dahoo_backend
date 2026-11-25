from rest_framework import serializers

from organizations.scoping import OrganizationScopedRelatedField
from owners.models import Owner
from properties.models import Building, Property, Unit
from properties.services import check_status_change


class PropertySerializer(serializers.ModelSerializer):
    # Bailleur de l'agence (/owners/) ; vide si l'agence possède le bien.
    owner = OrganizationScopedRelatedField(queryset=Owner.objects.all(), required=False, allow_null=True)
    owner_name = serializers.CharField(source="owner.full_name", read_only=True, default="")
    # Compteurs annotés par la vue (0 sur la réponse de création).
    buildings_count = serializers.IntegerField(read_only=True, default=0)
    units_count = serializers.IntegerField(read_only=True, default=0)
    occupied_units_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Property
        fields = [
            "id", "name", "owner", "owner_name", "commission_rate", "address", "city", "neighborhood", "latitude", "longitude",
            "buildings_count", "units_count", "occupied_units_count", "created_at",
        ]
        read_only_fields = ["created_at"]
        extra_kwargs = {
            "latitude": {"min_value": -90, "max_value": 90},
            "longitude": {"min_value": -180, "max_value": 180},
        }


class BuildingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Building
        fields = ["id", "property", "name"]
        read_only_fields = ["property"]


class UnitSerializer(serializers.ModelSerializer):
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    # « Résidence X · Bâtiment A · A101 », pour les sélecteurs des formulaires.
    label = serializers.CharField(read_only=True)

    class Meta:
        model = Unit
        fields = [
            "id", "building", "reference", "label", "category", "category_label", "unit_type", "surface",
            "bedrooms", "bathrooms", "parking_spaces", "is_furnished", "status",
        ]
        read_only_fields = ["building"]
        extra_kwargs = {"surface": {"min_value": 0}}

    def validate_status(self, value):
        return check_status_change(self.instance, value)


class UnitStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Unit.STATUS_CHOICES)

    def validate_status(self, value):
        return check_status_change(self.instance, value)
