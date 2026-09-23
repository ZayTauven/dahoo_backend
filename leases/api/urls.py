from django.urls import path

from .views import (
    LeaseActivateAPIView,
    LeaseCancelAPIView,
    LeaseCompleteAPIView,
    LeaseDetailAPIView,
    LeaseListCreateAPIView,
    LeaseTerminateAPIView,
)

urlpatterns = [
    path("", LeaseListCreateAPIView.as_view()),
    path("<int:pk>/", LeaseDetailAPIView.as_view()),
    path("<int:pk>/activate/", LeaseActivateAPIView.as_view()),
    path("<int:pk>/terminate/", LeaseTerminateAPIView.as_view()),
    path("<int:pk>/complete/", LeaseCompleteAPIView.as_view()),
    path("<int:pk>/cancel/", LeaseCancelAPIView.as_view()),
]
