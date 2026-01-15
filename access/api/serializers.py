from rest_framework import serializers
from access.models import Role, Capability, RoleCapability, UserRole, UserCapability


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ["id", "code", "label"]


class CapabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Capability
        fields = ["id", "code", "description"]


class RoleCapabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = RoleCapability
        fields = ["id", "role", "capability"]


class UserRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserRole
        fields = ["id", "user", "role", "active"]


class UserCapabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = UserCapability
        fields = ["id", "user", "capability", "context_type", "context_id"]
