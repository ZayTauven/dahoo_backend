from django.urls import path

from .views import (
    SubscriptionDetailAPIView,
    SubscriptionListAPIView,
    SubscriptionPaymentListAPIView,
    SubscriptionPlanDetailAPIView,
    SubscriptionPlanListCreateAPIView,
)

urlpatterns = [
    path("plans/", SubscriptionPlanListCreateAPIView.as_view()),
    path("plans/<int:pk>/", SubscriptionPlanDetailAPIView.as_view()),

    path("subscriptions/", SubscriptionListAPIView.as_view()),
    path("subscriptions/<int:pk>/", SubscriptionDetailAPIView.as_view()),

    path("payments/", SubscriptionPaymentListAPIView.as_view()),
]
