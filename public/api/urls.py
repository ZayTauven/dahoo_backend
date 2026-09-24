from django.urls import path

from .views import (
    DemoRequestCreateAPIView,
    PublicAgencyDetailAPIView,
    PublicAgencyListAPIView,
    PublicListingDetailAPIView,
    PublicListingInterestAPIView,
    PublicListingListAPIView,
    PublicPlanListAPIView,
    PublicStatsAPIView,
)

urlpatterns = [
    path("listings/", PublicListingListAPIView.as_view()),
    path("listings/<int:pk>/", PublicListingDetailAPIView.as_view()),
    path("listings/<int:pk>/interest/", PublicListingInterestAPIView.as_view()),
    path("agencies/", PublicAgencyListAPIView.as_view()),
    path("agencies/<int:pk>/", PublicAgencyDetailAPIView.as_view()),
    path("stats/", PublicStatsAPIView.as_view()),
    path("plans/", PublicPlanListAPIView.as_view()),
    path("demo-requests/", DemoRequestCreateAPIView.as_view()),
]
