from django.urls import path
from .views import (
    LeaseCreateAPIView,
    LeaseListAPIView,
    LeaseActivateAPIView,
    LeaseTerminateAPIView,
    LeaseCompleteAPIView,
    LeaseCancelAPIView,
)

urlpatterns = [
    path("", LeaseListAPIView.as_view()),
    path("create/", LeaseCreateAPIView.as_view()),
    path("<int:pk>/activate/", LeaseActivateAPIView.as_view()),
    path("<int:pk>/terminate/", LeaseTerminateAPIView.as_view()),
    path("<int:pk>/complete/", LeaseCompleteAPIView.as_view()),
    path("<int:pk>/cancel/", LeaseCancelAPIView.as_view()),
]
