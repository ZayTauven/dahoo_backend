from django.urls import path
from .views import (
    SubscriptionPlanListCreateAPIView,
    SubscriptionPlanDetailAPIView,
    SubscriptionListCreateAPIView,
    SubscriptionDetailAPIView,
    SubscriptionPaymentListAPIView,
)

urlpatterns = [
    path("plans/", SubscriptionPlanListCreateAPIView.as_view()),
    path("plans/<int:pk>/", SubscriptionPlanDetailAPIView.as_view()),

    path("subscriptions/", SubscriptionListCreateAPIView.as_view()),
    path("subscriptions/<int:pk>/", SubscriptionDetailAPIView.as_view()),

    path("payments/", SubscriptionPaymentListAPIView.as_view()),
]
