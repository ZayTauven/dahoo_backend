from django.urls import path

from .views import (
    AutomationRuleListCreateAPIView,
    InAppNotificationDetailAPIView,
    InAppNotificationListAPIView,
    InAppReadAllAPIView,
    InAppSummaryAPIView,
    NotificationDetailAPIView,
    NotificationListAPIView,
    NotificationTemplateListCreateAPIView,
)

urlpatterns = [
    path("", NotificationListAPIView.as_view()),
    path("<int:pk>/", NotificationDetailAPIView.as_view()),
    path("templates/", NotificationTemplateListCreateAPIView.as_view()),
    path("rules/", AutomationRuleListCreateAPIView.as_view()),
    path("inapp/", InAppNotificationListAPIView.as_view()),
    path("inapp/summary/", InAppSummaryAPIView.as_view()),
    path("inapp/read-all/", InAppReadAllAPIView.as_view()),
    path("inapp/<int:pk>/", InAppNotificationDetailAPIView.as_view()),
]
