from django.urls import path

from .platform import (
    PlatformDashboardAPIView,
    PlatformDemoRequestDetailAPIView,
    PlatformDemoRequestListAPIView,
    PlatformOrganizationDetailAPIView,
    PlatformOrganizationListCreateAPIView,
    PlatformOrganizationMembersAPIView,
    PlatformSubscriptionDetailAPIView,
    PlatformSubscriptionListCreateAPIView,
)

urlpatterns = [
    path("dashboard/", PlatformDashboardAPIView.as_view()),
    path("organizations/", PlatformOrganizationListCreateAPIView.as_view()),
    path("organizations/<int:pk>/", PlatformOrganizationDetailAPIView.as_view()),
    path("organizations/<int:pk>/members/", PlatformOrganizationMembersAPIView.as_view()),
    path("organizations/<int:pk>/subscriptions/", PlatformSubscriptionListCreateAPIView.as_view()),
    path("subscriptions/<int:pk>/", PlatformSubscriptionDetailAPIView.as_view()),
    path("demo-requests/", PlatformDemoRequestListAPIView.as_view()),
    path("demo-requests/<int:pk>/", PlatformDemoRequestDetailAPIView.as_view()),
]
