from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404

from users.api.permissions import HasCapability
from notifications.models import (
	Notification,
	NotificationTemplate,
	AutomationRule,
	InAppNotification,
)
from .serializers import (
	NotificationSerializer,
	NotificationTemplateSerializer,
	AutomationRuleSerializer,
	InAppNotificationSerializer,
)


class NotificationListCreateAPIView(generics.ListCreateAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "notification.view"
	serializer_class = NotificationSerializer

	def get_queryset(self):
		return Notification.objects.filter(user=self.request.user)


class NotificationDetailAPIView(generics.RetrieveAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "notification.view"
	queryset = Notification.objects.all()
	serializer_class = NotificationSerializer


class NotificationTemplateListCreateAPIView(generics.ListCreateAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "notification.template.view"
	queryset = NotificationTemplate.objects.all()
	serializer_class = NotificationTemplateSerializer


class AutomationRuleListCreateAPIView(generics.ListCreateAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "notification.rule.view"
	queryset = AutomationRule.objects.all()
	serializer_class = AutomationRuleSerializer


class InAppNotificationListCreateAPIView(generics.ListCreateAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "notification.inapp.view"
	serializer_class = InAppNotificationSerializer

	def get_queryset(self):
		return InAppNotification.objects.filter(user=self.request.user)

