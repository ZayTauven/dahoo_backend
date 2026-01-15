from django.urls import path
from .views import (
    NotificationListCreateAPIView,
    NotificationDetailAPIView,
    NotificationTemplateListCreateAPIView,
    AutomationRuleListCreateAPIView,
    InAppNotificationListCreateAPIView,
)

urlpatterns = [
    path("", NotificationListCreateAPIView.as_view()),
    path("<int:pk>/", NotificationDetailAPIView.as_view()),

    path("templates/", NotificationTemplateListCreateAPIView.as_view()),
    path("rules/", AutomationRuleListCreateAPIView.as_view()),

    path("inapp/", InAppNotificationListCreateAPIView.as_view()),
]
