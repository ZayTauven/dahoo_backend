from django.urls import path

from .views import BuildingKPIListAPIView, DashboardAPIView, FinancialSnapshotListAPIView, InsightListAPIView

urlpatterns = [
    path("dashboard/", DashboardAPIView.as_view()),
    path("kpis/", BuildingKPIListAPIView.as_view()),
    path("snapshots/", FinancialSnapshotListAPIView.as_view()),
    path("insights/", InsightListAPIView.as_view()),
]
