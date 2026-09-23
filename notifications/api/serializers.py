from rest_framework import serializers

from notifications.models import AutomationRule, InAppNotification, Notification, NotificationTemplate
from organizations.scoping import OrganizationScopedRelatedField


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "channel", "subject", "message", "status", "scheduled_at", "sent_at", "created_at"]
        read_only_fields = fields


class NotificationTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationTemplate
        fields = ["id", "event_type", "channel", "subject_template", "body_template", "active"]


class AutomationRuleSerializer(serializers.ModelSerializer):
    template = OrganizationScopedRelatedField(queryset=NotificationTemplate.objects.all())

    class Meta:
        model = AutomationRule
        fields = ["id", "event", "active", "delay_minutes", "channel", "template"]


class InAppNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = InAppNotification
        fields = ["id", "title", "body", "read", "created_at"]
        read_only_fields = ["title", "body", "created_at"]
