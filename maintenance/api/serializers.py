from django.contrib.auth import get_user_model
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from maintenance.models import (
    MaintenanceAssignment,
    MaintenanceCategory,
    MaintenanceLog,
    MaintenanceTicket,
)
from organizations.scoping import OrganizationScopedRelatedField
from properties.models import Unit

User = get_user_model()


def full_name(user):
    return f"{user.first_name} {user.last_name}".strip() or user.phone if user else ""


class MaintenanceCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = MaintenanceCategory
        fields = ["id", "code", "label"]


class MaintenanceTicketSerializer(serializers.ModelSerializer):
    unit = OrganizationScopedRelatedField(
        queryset=Unit.objects.all(), organization_lookup="building__property__organization"
    )
    unit_label = serializers.CharField(source="unit.label", read_only=True)
    category_label = serializers.CharField(source="category.label", read_only=True, allow_null=True)
    reported_by_name = serializers.SerializerMethodField()
    # Affectation en cours (la plus récente), calculée par tickets_with_labels().
    assigned_to = serializers.IntegerField(source="current_assignee_id", read_only=True, allow_null=True, default=None)
    assigned_to_name = serializers.SerializerMethodField()
    assigned_at = serializers.DateTimeField(source="current_assigned_at", read_only=True, allow_null=True, default=None)

    class Meta:
        model = MaintenanceTicket
        fields = [
            "id",
            "unit",
            "unit_label",
            "category",
            "category_label",
            "reported_by",
            "reported_by_name",
            "assigned_to",
            "assigned_to_name",
            "assigned_at",
            "description",
            "priority",
            "status",
            "created_at",
            "updated_at",
        ]
        # Le statut change uniquement via l'action dédiée (capability distincte).
        read_only_fields = ["reported_by", "status", "created_at", "updated_at"]

    @extend_schema_field(OpenApiTypes.STR)
    def get_reported_by_name(self, ticket):
        return full_name(ticket.reported_by)

    @extend_schema_field({"type": "string", "nullable": True})
    def get_assigned_to_name(self, ticket):
        first = getattr(ticket, "current_assignee_first", None)
        last = getattr(ticket, "current_assignee_last", None)
        return f"{first or ''} {last or ''}".strip() or None


class TicketStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=MaintenanceTicket.STATUS_CHOICES)


class ActiveMemberField(serializers.PrimaryKeyRelatedField):
    """Utilisateur membre actif de l'organisation active (conditions dans un seul filter())."""

    def get_queryset(self):
        organization = getattr(self.context.get("request"), "organization", None)
        if organization is None:
            return User.objects.none()
        return User.objects.filter(
            memberships__organization=organization, memberships__is_active=True
        ).distinct()


class MaintenanceAssignmentSerializer(serializers.ModelSerializer):
    # Seuls les membres actifs de l'organisation peuvent recevoir un ticket.
    assigned_to = ActiveMemberField()

    class Meta:
        model = MaintenanceAssignment
        fields = ["id", "ticket", "assigned_to", "assigned_by", "assigned_at"]
        read_only_fields = ["ticket", "assigned_by", "assigned_at"]


class MaintenanceLogSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = MaintenanceLog
        fields = ["id", "ticket", "user", "user_name", "message", "created_at"]
        read_only_fields = ["user", "created_at", "ticket"]

    @extend_schema_field(OpenApiTypes.STR)
    def get_user_name(self, log):
        return full_name(log.user)
