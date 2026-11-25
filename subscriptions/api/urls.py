from django.urls import path

from .views import (
    PlanRequestCreateAPIView,
    SubscriptionDetailAPIView,
    SubscriptionListAPIView,
    SubscriptionOverviewAPIView,
    SubscriptionPaymentListAPIView,
    SubscriptionPaymentReceiptAPIView,
    SubscriptionPlanListAPIView,
)

urlpatterns = [
    path("plans/", SubscriptionPlanListAPIView.as_view()),
    path("overview/", SubscriptionOverviewAPIView.as_view()),
    path("requests/", PlanRequestCreateAPIView.as_view()),

    path("subscriptions/", SubscriptionListAPIView.as_view()),
    path("subscriptions/<int:pk>/", SubscriptionDetailAPIView.as_view()),

    path("payments/", SubscriptionPaymentListAPIView.as_view()),
    path("payments/<int:pk>/receipt/", SubscriptionPaymentReceiptAPIView.as_view()),
]
