from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from mailing.addresses import is_deliverable
from organizations.models import Organization
from organizations.theme import OrganizationThemeSerializer
from subscriptions.services import get_access_status, get_active_subscription
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
    organization_kind = serializers.ChoiceField(source="organization.kind", choices=Organization.KINDS)
    role = serializers.CharField(source="role.code")
    role_label = serializers.CharField(source="role.label")
    trial_ends_at = serializers.DateTimeField(source="organization.trial_ends_at")
    access_status = serializers.SerializerMethodField()
    # Échéance de l'abonnement en cours (null : essai, accès sans échéance ou compte interne).
    subscription_ends_on = serializers.SerializerMethodField()
    # Apparence choisie par les administrateurs : appliquée à tous les membres, quel que soit leur rôle.
    organization_theme = OrganizationThemeSerializer(source="organization.theme", read_only=True)

    @extend_schema_field(serializers.ChoiceField(choices=["ACTIVE", "TRIAL", "EXPIRED"]))
    def get_access_status(self, obj):
        return get_access_status(obj.organization)

    @extend_schema_field(serializers.DateField(allow_null=True))
    def get_subscription_ends_on(self, obj):
        subscription = get_active_subscription(obj.organization)
        return subscription.end_date if subscription else None


class MeSerializer(serializers.ModelSerializer):
    memberships = serializers.SerializerMethodField()
    # Admin Dahoo : accès à l'espace plateforme (/api/v1/platform/)
    is_platform_admin = serializers.BooleanField(source="is_staff", read_only=True)
    email_verified = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id", "phone", "email", "email_verified", "email_digest", "email_alerts", "first_name", "last_name",
            "is_platform_admin", "memberships",
        )
        read_only_fields = ("phone", "email", "first_name", "last_name")

    def get_email_verified(self, user) -> bool:
        return bool(user.email and user.email_verified_at)

    @extend_schema_field(MeMembershipSerializer(many=True))
    def get_memberships(self, user):
        memberships = user.memberships.filter(is_active=True, organization__is_active=True).select_related(
            "organization", "role"
        )
        return MeMembershipSerializer(memberships, many=True).data


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_current_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Mot de passe actuel incorrect.")
        return value

    def validate_new_password(self, value):
        validate_password(value, self.context["request"].user)
        return value


class ForgotPasswordSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=30)


class ResetPasswordSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True)


class ConfirmEmailSerializer(serializers.Serializer):
    token = serializers.CharField()


class ChangeEmailSerializer(serializers.Serializer):
    email = serializers.EmailField()
    current_password = serializers.CharField(write_only=True)

    def validate_current_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Mot de passe incorrect.")
        return value

    def validate_email(self, value):
        if not is_deliverable(value):
            raise serializers.ValidationError("Cette adresse ne peut pas recevoir de message.")
        return value.lower()


class TemporaryPasswordSerializer(serializers.Serializer):
    temporary_password = serializers.CharField(help_text="Affiché une seule fois")


class MeCapabilitiesSerializer(serializers.Serializer):
    organization_id = serializers.IntegerField()
    role = serializers.CharField(allow_null=True)
    capabilities = serializers.ListField(child=serializers.CharField())
