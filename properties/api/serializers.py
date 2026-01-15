from rest_framework import serializers
from properties.models import Property, Building, Unit


class PropertySerializer(serializers.ModelSerializer):
    class Meta:
        model = Property
        fields = ["id", "name", "owner", "address", "city", "created_at"]
        read_only_fields = ["owner", "created_at"]


class PropertyCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Property
        fields = ["name", "address", "city"]


class BuildingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Building
        fields = ["id", "property", "name"]
        read_only_fields = ["property"]


class BuildingCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Building
        fields = ["name"]


class UnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Unit
        fields = ["id", "building", "reference", "unit_type", "surface", "status"]
        read_only_fields = ["building"]


class UnitCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Unit
        fields = ["reference", "unit_type", "surface", "status"]
