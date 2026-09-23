from rest_framework import generics

from analytics.models import BuildingKPI, FinancialSnapshot, Insight
from organizations.scoping import OrganizationScopedMixin

from .serializers import (
	BuildingKPISerializer,
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
