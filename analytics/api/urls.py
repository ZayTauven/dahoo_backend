from django.urls import path

from .views import BuildingKPIListAPIView, FinancialSnapshotListAPIView, InsightListAPIView

urlpatterns = [
    path("kpis/", BuildingKPIListAPIView.as_view()),
    path("snapshots/", FinancialSnapshotListAPIView.as_view()),
    path("insights/", InsightListAPIView.as_view()),
]
