from django.urls import path
from .views import (
    BuildingKPIListCreateAPIView,
    FinancialSnapshotListCreateAPIView,
    InsightListCreateAPIView,
)

urlpatterns = [
    path("kpis/", BuildingKPIListCreateAPIView.as_view()),
    path("snapshots/", FinancialSnapshotListCreateAPIView.as_view()),
    path("insights/", InsightListCreateAPIView.as_view()),
]
