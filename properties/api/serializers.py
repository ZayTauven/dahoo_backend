from django.contrib.auth import get_user_model
from rest_framework import serializers

from properties.models import Building, Property, Unit

User = get_user_model()


class PropertySerializer(serializers.ModelSerializer):
    # Le bailleur est un compte existant ; le rattacher n'expose que son identifiant.
    owner = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, allow_null=True)

    class Meta:
        model = Property
        fields = ["id", "name", "owner", "address", "city", "created_at"]
        read_only_fields = ["created_at"]


class BuildingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Building
        fields = ["id", "property", "name"]
        read_only_fields = ["property"]


class UnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Unit
        fields = ["id", "building", "reference", "unit_type", "surface", "status"]
        read_only_fields = ["building"]
        extra_kwargs = {"surface": {"min_value": 0}}


class UnitStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Unit.STATUS_CHOICES)
