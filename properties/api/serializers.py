from django.contrib.auth import get_user_model
from rest_framework import serializers

from properties.models import Building, Property, Unit

User = get_user_model()


class PropertySerializer(serializers.ModelSerializer):
    # Le bailleur est un compte existant ; le rattacher n'expose que son identifiant.
    owner = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, allow_null=True)
    # Compteurs annotés par la vue (0 sur la réponse de création).
    buildings_count = serializers.IntegerField(read_only=True, default=0)
    units_count = serializers.IntegerField(read_only=True, default=0)
    occupied_units_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Property
        fields = [
            "id", "name", "owner", "address", "city", "neighborhood", "latitude", "longitude",
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


class UnitStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Unit.STATUS_CHOICES)
