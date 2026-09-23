from rest_framework import serializers

from access.models import Capability, Role


class CapabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Capability
        fields = ["id", "code", "description"]


class RoleSerializer(serializers.ModelSerializer):
    capabilities = serializers.SlugRelatedField(slug_field="code", many=True, read_only=True)

    class Meta:
        model = Role
        fields = ["id", "code", "label", "capabilities"]
