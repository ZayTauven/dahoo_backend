from rest_framework import serializers
from maintenance.models import (
    MaintenanceCategory,
    MaintenanceTicket,
    MaintenanceAssignment,
    MaintenanceLog,
)


class MaintenanceCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = MaintenanceCategory
        fields = ["id", "code", "label"]


class MaintenanceTicketSerializer(serializers.ModelSerializer):
    class Meta:
        model = MaintenanceTicket
        fields = [
            "id",
            "unit",
            "category",
            "reported_by",
            "description",
            "priority",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["reported_by", "created_at", "updated_at"]


class MaintenanceTicketCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = MaintenanceTicket
        fields = ["unit", "category", "description", "priority"]


class MaintenanceAssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = MaintenanceAssignment
        fields = ["id", "ticket", "assigned_to", "assigned_by", "assigned_at"]
        read_only_fields = ["assigned_by", "assigned_at"]


class MaintenanceLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = MaintenanceLog
        fields = ["id", "ticket", "user", "message", "created_at"]
        read_only_fields = ["user", "created_at", "ticket"]
