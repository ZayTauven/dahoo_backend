from django.urls import path

from .views import CapabilityListAPIView, RoleListAPIView

urlpatterns = [
    path("roles/", RoleListAPIView.as_view()),
    path("capabilities/", CapabilityListAPIView.as_view()),
]
