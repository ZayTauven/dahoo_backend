from django.urls import path
from .views import LoginAPIView, MeAPIView, MeCapabilitiesAPIView
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    path("login/", LoginAPIView.as_view()),
    path("refresh/", TokenRefreshView.as_view()),
    path("me/", MeAPIView.as_view()),
    path("me/capabilities/", MeCapabilitiesAPIView.as_view()),
]
