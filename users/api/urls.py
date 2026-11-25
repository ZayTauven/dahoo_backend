from django.urls import path
from .views import (
    ChangeEmailAPIView,
    ChangePasswordAPIView,
    ConfirmEmailAPIView,
    ForgotPasswordAPIView,
    LoginAPIView,
    MeAPIView,
    MeCapabilitiesAPIView,
    ResetPasswordAPIView,
)
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    path("login/", LoginAPIView.as_view()),
    path("refresh/", TokenRefreshView.as_view()),
    path("me/", MeAPIView.as_view()),
    path("password/forgot/", ForgotPasswordAPIView.as_view()),
    path("password/reset/", ResetPasswordAPIView.as_view()),
    path("email/confirm/", ConfirmEmailAPIView.as_view()),
    path("me/email/", ChangeEmailAPIView.as_view()),
    path("me/password/", ChangePasswordAPIView.as_view()),
    path("me/capabilities/", MeCapabilitiesAPIView.as_view()),
]
