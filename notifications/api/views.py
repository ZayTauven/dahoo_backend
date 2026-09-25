from django.db.models import Q
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.exceptions import APIException
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from notifications.models import (
	AutomationRule,
	InAppNotification,
	Notification,
	NotificationTemplate,
)
from notifications.services import sync_platform_reminders, sync_reminders
from organizations.context import resolve_organization
from organizations.scoping import OrganizationScopedMixin

from .serializers import (
	AutomationRuleSerializer,
	InAppNotificationSerializer,
	InAppReadAllSerializer,
	InAppSummarySerializer,
	NotificationSerializer,
	NotificationTemplateSerializer,
)


# Notifications personnelles : chaque utilisateur ne voit que les siennes.
# Elles sont créées par le serveur (règles d'automatisation), jamais via l'API.
class NotificationListAPIView(generics.ListAPIView):
	permission_classes = [IsAuthenticated]
	serializer_class = NotificationSerializer
	queryset = Notification.objects.none()  # Modèle de référence pour le schéma OpenAPI (le vrai queryset dépend de la requête).

	def get_queryset(self):
		return Notification.objects.filter(user=self.request.user).order_by("-created_at")


class NotificationDetailAPIView(generics.RetrieveAPIView):
	permission_classes = [IsAuthenticated]
	serializer_class = NotificationSerializer

	def get_queryset(self):
		return Notification.objects.filter(user=self.request.user)


def inapp_scope(request, *, sync=False):
	"""
	Notifications visibles : celles de l'agence active et celles de la plateforme (organisation vide).
	Un compte sans agence (équipe Dahoo) ne voit que les secondes. `sync` crée d'abord les rappels dus.
	"""
	try:
		organization = resolve_organization(request)
	except APIException:
		organization = None
	if sync:
		if organization is not None:
			sync_reminders(organization)
		if request.user.is_staff:
			sync_platform_reminders()
	scope = Q(organization__isnull=True)
	if organization is not None:
		scope |= Q(organization=organization)
	return InAppNotification.objects.filter(scope, user=request.user)


@extend_schema(parameters=[OpenApiParameter("unread", OpenApiTypes.BOOL, description="Seulement les non lues.")])
class InAppNotificationListAPIView(generics.ListAPIView):
	permission_classes = [IsAuthenticated]
	serializer_class = InAppNotificationSerializer
	queryset = InAppNotification.objects.none()  # Modèle de référence pour le schéma OpenAPI (le vrai queryset dépend de la requête).

	def get_queryset(self):
		queryset = inapp_scope(self.request, sync=True).order_by("-created_at", "-id")
		if self.request.query_params.get("unread") in ("1", "true"):
			queryset = queryset.filter(read=False)
		return queryset


class InAppSummaryAPIView(APIView):
	"""Nombre de notifications non lues (pastille de la cloche, interrogée régulièrement)."""

	permission_classes = [IsAuthenticated]

	@extend_schema(responses=InAppSummarySerializer)
	def get(self, request):
		return Response({"unread": inapp_scope(request, sync=True).filter(read=False).count()})


class InAppReadAllAPIView(APIView):
	"""Marque comme lues toutes les notifications visibles (agence active et plateforme)."""

	permission_classes = [IsAuthenticated]

	@extend_schema(request=None, responses=InAppReadAllSerializer)
	def post(self, request):
		return Response({"updated": inapp_scope(request).filter(read=False).update(read=True)})


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
