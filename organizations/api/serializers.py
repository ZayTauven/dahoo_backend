from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from access.models import Role
from organizations.models import Membership, Organization
from organizations.services import add_member, validate_new_member
from users.phone import PhoneField
from subscriptions.services import get_access_status

User = get_user_model()


class OrganizationSerializer(serializers.ModelSerializer):
    access_status = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = [
            "id", "name", "phone", "email", "address", "city", "logo",
            "is_active", "trial_ends_at", "access_status", "created_at",
        ]
        read_only_fields = ["logo", "is_active", "trial_ends_at", "created_at"]

    @extend_schema_field(serializers.ChoiceField(choices=["ACTIVE", "TRIAL", "EXPIRED"]))
    def get_access_status(self, obj):
        return get_access_status(obj)


class MemberUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "phone", "email", "first_name", "last_name"]


class MembershipSerializer(serializers.ModelSerializer):
    user = MemberUserSerializer(read_only=True)
    role = serializers.SlugRelatedField(slug_field="code", queryset=Role.objects.all())

    class Meta:
        model = Membership
        fields = ["id", "user", "role", "is_active", "created_at"]
        read_only_fields = ["created_at"]


class NewMemberFieldsMixin(serializers.Serializer):
    phone = PhoneField(max_length=20)
    first_name = serializers.CharField(max_length=100, required=False)
    last_name = serializers.CharField(max_length=100, required=False)
    email = serializers.EmailField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, required=False)


class MembershipCreateSerializer(NewMemberFieldsMixin):
    """
    Ajoute un membre par numéro de téléphone. Si aucun compte n'existe pour ce numéro,
    il est créé (prénom, nom et mot de passe requis).
    """

    role = serializers.SlugRelatedField(slug_field="code", queryset=Role.objects.all())

    def validate(self, attrs):
        attrs["existing_user"] = validate_new_member(self.context["request"].organization, attrs)
        return attrs

    def create(self, validated_data):
        role = validated_data.pop("role")
        return add_member(self.context["request"].organization, role, **validated_data)
