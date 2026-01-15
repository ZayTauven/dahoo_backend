from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from users.api.permissions import HasCapability
from analytics.models import BuildingKPI, FinancialSnapshot, Insight
from .serializers import (
	BuildingKPISerializer,
	FinancialSnapshotSerializer,
	InsightSerializer,
)


class BuildingKPIListCreateAPIView(generics.ListCreateAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "analytics.kpi.view"
	queryset = BuildingKPI.objects.all()
	serializer_class = BuildingKPISerializer


class FinancialSnapshotListCreateAPIView(generics.ListCreateAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "analytics.financial.view"
	queryset = FinancialSnapshot.objects.all()
	serializer_class = FinancialSnapshotSerializer


class InsightListCreateAPIView(generics.ListCreateAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "analytics.insight.view"
	queryset = Insight.objects.all()
	serializer_class = InsightSerializer

