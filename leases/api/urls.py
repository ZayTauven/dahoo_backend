from django.urls import path

from deposits.api.views import LeaseDepositAPIView, SettleDepositAPIView
from inspections.api.views import LeaseInspectionsAPIView

from .views import (
    LeaseActivateAPIView,
    LeaseAutoSchedulesAPIView,
    LeaseCancelAPIView,
    LeaseCompleteAPIView,
    LeaseDetailAPIView,
    LeaseListCreateAPIView,
    LeaseTerminateAPIView,
    TenantDetailAPIView,
    TenantListCreateAPIView,
)

urlpatterns = [
    path("", LeaseListCreateAPIView.as_view()),
    path("tenants/", TenantListCreateAPIView.as_view()),
    path("tenants/<int:pk>/", TenantDetailAPIView.as_view()),
    path("<int:pk>/", LeaseDetailAPIView.as_view()),
    path("<int:pk>/activate/", LeaseActivateAPIView.as_view()),
    path("<int:pk>/terminate/", LeaseTerminateAPIView.as_view()),
    path("<int:pk>/complete/", LeaseCompleteAPIView.as_view()),
    path("<int:pk>/cancel/", LeaseCancelAPIView.as_view()),
    path("<int:pk>/inspections/", LeaseInspectionsAPIView.as_view()),
    path("<int:pk>/deposit/", LeaseDepositAPIView.as_view()),
    path("<int:pk>/deposit/settle/", SettleDepositAPIView.as_view()),
    path("<int:pk>/auto-schedules/", LeaseAutoSchedulesAPIView.as_view()),
]
