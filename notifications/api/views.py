from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from notifications.models import (
	AutomationRule,
	InAppNotification,
	Notification,
	NotificationTemplate,
)
from organizations.scoping import OrganizationScopedMixin

from .serializers import (
	AutomationRuleSerializer,
	InAppNotificationSerializer,
	NotificationSerializer,
	NotificationTemplateSerializer,
)


# Notifications personnelles : chaque utilisateur ne voit que les siennes.
# Elles sont créées par le serveur (règles d'automatisation), jamais via l'API.
class NotificationListAPIView(generics.ListAPIView):
	permission_classes = [IsAuthenticated]
	serializer_class = NotificationSerializer

	def get_queryset(self):
		return Notification.objects.filter(user=self.request.user).order_by("-created_at")


class NotificationDetailAPIView(generics.RetrieveAPIView):
	permission_classes = [IsAuthenticated]
	serializer_class = NotificationSerializer

	def get_queryset(self):
		return Notification.objects.filter(user=self.request.user)


class InAppNotificationListAPIView(generics.ListAPIView):
	permission_classes = [IsAuthenticated]
	serializer_class = InAppNotificationSerializer

	def get_queryset(self):
		return InAppNotification.objects.filter(user=self.request.user).order_by("-created_at")


class InAppNotificationDetailAPIView(generics.RetrieveUpdateAPIView):
	"""Permet de marquer une notification comme lue (PATCH {"read": true})."""

	permission_classes = [IsAuthenticated]
	serializer_class = InAppNotificationSerializer
	http_method_names = ["get", "patch", "head", "options"]

	def get_queryset(self):
		return InAppNotification.objects.filter(user=self.request.user)


class NotificationTemplateListCreateAPIView(OrganizationScopedMixin, generics.ListCreateAPIView):
	capability_resource = "notification.template"
	queryset = NotificationTemplate.objects.order_by("event_type")
	serializer_class = NotificationTemplateSerializer

	def perform_create(self, serializer):
		serializer.save(organization=self.organization)


class AutomationRuleListCreateAPIView(OrganizationScopedMixin, generics.ListCreateAPIView):
	capability_resource = "notification.rule"
	queryset = AutomationRule.objects.order_by("event")
	serializer_class = AutomationRuleSerializer

	def perform_create(self, serializer):
		serializer.save(organization=self.organization)
