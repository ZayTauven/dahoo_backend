from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from access.catalog import CAPABILITIES
from access.permissions import HasCapability, get_membership_capabilities
from analytics.dashboard import build_dashboard

from analytics.models import BuildingKPI, FinancialSnapshot, Insight
from organizations.scoping import OrganizationScopedMixin

from .serializers import (
	BuildingKPISerializer,
	DashboardSerializer,
	FinancialSnapshotSerializer,
	InsightSerializer,
)


# Les indicateurs sont calculés côté serveur : l'API les expose en lecture seule.
class BuildingKPIListAPIView(OrganizationScopedMixin, generics.ListAPIView):
	required_capability = "analytics.kpi.view"
	organization_lookup = "building__property__organization"
	queryset = BuildingKPI.objects.order_by("-period_start")
	serializer_class = BuildingKPISerializer


class FinancialSnapshotListAPIView(OrganizationScopedMixin, generics.ListAPIView):
	required_capability = "analytics.financial.view"
	queryset = FinancialSnapshot.objects.order_by("-month")
	serializer_class = FinancialSnapshotSerializer


class InsightListAPIView(OrganizationScopedMixin, generics.ListAPIView):
	required_capability = "analytics.insight.view"
	queryset = Insight.objects.order_by("-created_at")
	serializer_class = InsightSerializer


class DashboardAPIView(APIView):
	"""
	Tableau de bord de l'agence active : portefeuille, baux, finances (12 derniers mois par défaut),
	maintenance, annonces et alertes. Chaque section vaut `null` si le rôle ne permet pas de la voir.
	"""

	permission_classes = [HasCapability]
	required_capability = "analytics.kpi.view"

	@extend_schema(
		parameters=[OpenApiParameter("months", int, description="Nombre de mois d'historique : 6 ou 12 (défaut 12).")],
		responses=DashboardSerializer,
	)
	def get(self, request):
		try:
			months = int(request.query_params.get("months", 12))
		except ValueError:
			months = 12
		months = 6 if months <= 6 else 12
		capabilities = set(CAPABILITIES) if request.user.is_superuser else get_membership_capabilities(request)
		data = build_dashboard(request.organization, capabilities, months=months, request=request)
		return Response(DashboardSerializer(data).data)
