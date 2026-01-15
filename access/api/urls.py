from django.urls import path
from .views import (
    RoleListCreateAPIView,
    RoleDetailAPIView,
    CapabilityListCreateAPIView,
    UserRoleListCreateAPIView,
    UserCapabilityListCreateAPIView,
)

urlpatterns = [
    path("roles/", RoleListCreateAPIView.as_view()),
    path("roles/<int:pk>/", RoleDetailAPIView.as_view()),

    path("capabilities/", CapabilityListCreateAPIView.as_view()),

    path("user-roles/", UserRoleListCreateAPIView.as_view()),
    path("user-capabilities/", UserCapabilityListCreateAPIView.as_view()),
]
