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
        fields = ["id", "kind", "title", "body", "link", "read", "created_at"]
        read_only_fields = ["kind", "title", "body", "link", "created_at"]


class InAppSummarySerializer(serializers.Serializer):
    unread = serializers.IntegerField()


class InAppReadAllSerializer(serializers.Serializer):
    updated = serializers.IntegerField()
