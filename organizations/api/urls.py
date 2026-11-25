from django.urls import path

from .views import (
    CurrentOrganizationAPIView,
    MemberDetailAPIView,
    MemberListCreateAPIView,
    MemberResetPasswordAPIView,
)

urlpatterns = [
    path("current/", CurrentOrganizationAPIView.as_view()),
    path("members/", MemberListCreateAPIView.as_view()),
    path("members/<int:pk>/", MemberDetailAPIView.as_view()),
    path("members/<int:pk>/reset-password/", MemberResetPasswordAPIView.as_view()),
]
