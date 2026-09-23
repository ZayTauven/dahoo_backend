from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from access.models import Role
from organizations.models import Membership, Organization

User = get_user_model()


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ["id", "name", "phone", "email", "address", "city", "is_active", "created_at"]
        read_only_fields = ["is_active", "created_at"]


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


class MembershipCreateSerializer(serializers.Serializer):
    """
    Ajoute un membre par numéro de téléphone. Si aucun compte n'existe pour ce numéro,
    il est créé (prénom, nom et mot de passe requis).
    """

    phone = serializers.CharField(max_length=20)
    first_name = serializers.CharField(max_length=100, required=False)
    last_name = serializers.CharField(max_length=100, required=False)
    email = serializers.EmailField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, required=False)
    role = serializers.SlugRelatedField(slug_field="code", queryset=Role.objects.all())

    def validate(self, attrs):
        organization = self.context["request"].organization
        user = User.objects.filter(phone=attrs["phone"]).first()
        if user and Membership.objects.filter(user=user, organization=organization).exists():
            raise serializers.ValidationError({"phone": "Cet utilisateur est déjà membre de l'organisation."})
        if user is None:
            missing = [f for f in ("first_name", "last_name", "password") if not attrs.get(f)]
            if missing:
                raise serializers.ValidationError(
                    {f: "Obligatoire pour créer un nouveau compte." for f in missing}
                )
            validate_password(attrs["password"])
        attrs["existing_user"] = user
        return attrs

    def create(self, validated_data):
        user = validated_data["existing_user"]
        if user is None:
            user = User.objects.create_user(
                phone=validated_data["phone"],
                password=validated_data["password"],
                first_name=validated_data["first_name"],
                last_name=validated_data["last_name"],
                email=validated_data.get("email") or None,
            )
        return Membership.objects.create(
            user=user,
            organization=self.context["request"].organization,
            role=validated_data["role"],
        )
