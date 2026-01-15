from rest_framework import serializers
from notifications.models import Notification, NotificationTemplate, AutomationRule, InAppNotification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "user", "channel", "subject", "message", "status", "scheduled_at", "sent_at", "created_at"]


class NotificationTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationTemplate
        fields = ["id", "event_type", "channel", "subject_template", "body_template", "active"]


class AutomationRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = AutomationRule
        fields = ["id", "event", "active", "delay_minutes", "channel", "template"]


class InAppNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = InAppNotification
        fields = ["id", "user", "title", "body", "read", "created_at"]
