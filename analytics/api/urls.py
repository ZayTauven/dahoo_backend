from django.urls import path

from .views import BuildingKPIListAPIView, DashboardAPIView, FinancialSnapshotListAPIView, InsightListAPIView, NavCountersAPIView

urlpatterns = [
    path("dashboard/", DashboardAPIView.as_view()),
    path("counters/", NavCountersAPIView.as_view()),
    path("kpis/", BuildingKPIListAPIView.as_view()),
    path("snapshots/", FinancialSnapshotListAPIView.as_view()),
    path("insights/", InsightListAPIView.as_view()),
]
