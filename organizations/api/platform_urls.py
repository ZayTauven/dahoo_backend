from django.urls import path

from .platform import (
    PlatformOrganizationDetailAPIView,
    PlatformOrganizationListCreateAPIView,
    PlatformOrganizationMembersAPIView,
    PlatformSubscriptionDetailAPIView,
    PlatformSubscriptionListCreateAPIView,
)

urlpatterns = [
    path("organizations/", PlatformOrganizationListCreateAPIView.as_view()),
    path("organizations/<int:pk>/", PlatformOrganizationDetailAPIView.as_view()),
    path("organizations/<int:pk>/members/", PlatformOrganizationMembersAPIView.as_view()),
    path("organizations/<int:pk>/subscriptions/", PlatformSubscriptionListCreateAPIView.as_view()),
    path("subscriptions/<int:pk>/", PlatformSubscriptionDetailAPIView.as_view()),
]
