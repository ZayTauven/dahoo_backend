from django.contrib.auth import get_user_model
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

    class Meta:
        model = MaintenanceTicket
        fields = [
            "id",
            "unit",
            "unit_label",
            "category",
            "category_label",
            "reported_by",
            "description",
            "priority",
            "status",
            "created_at",
            "updated_at",
        ]
        # Le statut change uniquement via l'action dédiée (capability distincte).
        read_only_fields = ["reported_by", "status", "created_at", "updated_at"]


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
    class Meta:
        model = MaintenanceLog
        fields = ["id", "ticket", "user", "message", "created_at"]
        read_only_fields = ["user", "created_at", "ticket"]
