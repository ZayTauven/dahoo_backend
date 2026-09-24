from django.contrib.auth import authenticate, get_user_model
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from subscriptions.services import get_access_status
from users.phone import normalize_phone


User = get_user_model()


class LoginSerializer(serializers.Serializer):
    phone = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = authenticate(
            request=self.context.get("request"),
            phone=normalize_phone(attrs["phone"]),
            password=attrs["password"],
        )
        if not user:
            raise serializers.ValidationError("Identifiants invalides")
        attrs["user"] = user
        return attrs


class MeMembershipSerializer(serializers.Serializer):
    organization_id = serializers.IntegerField(source="organization.id")
    organization_name = serializers.CharField(source="organization.name")
    role = serializers.CharField(source="role.code")
    role_label = serializers.CharField(source="role.label")
    trial_ends_at = serializers.DateTimeField(source="organization.trial_ends_at")
    access_status = serializers.SerializerMethodField()

    @extend_schema_field(serializers.ChoiceField(choices=["ACTIVE", "TRIAL", "EXPIRED"]))
    def get_access_status(self, obj):
        return get_access_status(obj.organization)


class MeSerializer(serializers.ModelSerializer):
    memberships = serializers.SerializerMethodField()
    # Admin Dahoo : accès à l'espace plateforme (/api/v1/platform/)
    is_platform_admin = serializers.BooleanField(source="is_staff", read_only=True)

    class Meta:
        model = User
        fields = ("id", "phone", "email", "first_name", "last_name", "is_platform_admin", "memberships")

    @extend_schema_field(MeMembershipSerializer(many=True))
    def get_memberships(self, user):
        memberships = user.memberships.filter(is_active=True, organization__is_active=True).select_related(
            "organization", "role"
        )
        return MeMembershipSerializer(memberships, many=True).data


class MeCapabilitiesSerializer(serializers.Serializer):
    organization_id = serializers.IntegerField()
    role = serializers.CharField(allow_null=True)
    capabilities = serializers.ListField(child=serializers.CharField())
