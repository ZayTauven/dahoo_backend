from django.contrib.auth import authenticate, get_user_model
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers


User = get_user_model()


class LoginSerializer(serializers.Serializer):
    phone = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = authenticate(
            request=self.context.get("request"),
            phone=attrs["phone"],
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


class MeSerializer(serializers.ModelSerializer):
    memberships = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "phone", "email", "first_name", "last_name", "is_superuser", "memberships")

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
