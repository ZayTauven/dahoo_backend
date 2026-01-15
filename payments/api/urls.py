from django.urls import path
from .views import (
    PaymentMethodListCreateAPIView,
    PaymentMethodDetailAPIView,
    PaymentScheduleListAPIView,
    PaymentScheduleDetailAPIView,
    PaymentListCreateAPIView,
    PaymentDetailAPIView,
    PaymentAllocateAPIView,
)

urlpatterns = [
    path("methods/", PaymentMethodListCreateAPIView.as_view()),
    path("methods/<int:pk>/", PaymentMethodDetailAPIView.as_view()),

    path("schedules/", PaymentScheduleListAPIView.as_view()),
    path("schedules/<int:pk>/", PaymentScheduleDetailAPIView.as_view()),

    path("payments/", PaymentListCreateAPIView.as_view()),
    path("payments/<int:pk>/", PaymentDetailAPIView.as_view()),
    path("payments/<int:pk>/allocate/", PaymentAllocateAPIView.as_view()),
]
