from django.urls import path
from .views import (
    CollectRentAPIView,
    PaymentCancelAPIView,
    PaymentReceiptAPIView,
    PaymentReceiptEmailAPIView,
    PaymentReceiptShareAPIView,
    ReminderPreviewAPIView,
    RentReceiptAPIView,
    RentReceiptEmailAPIView,
    RentReceiptShareAPIView,
    RentReminderListCreateAPIView,
    RentRollAPIView,
    PaymentMethodListCreateAPIView,
    PaymentMethodDetailAPIView,
    PaymentScheduleListCreateAPIView,
    PaymentScheduleDetailAPIView,
    PaymentListCreateAPIView,
    PaymentDetailAPIView,
    PaymentAllocateAPIView,
)

urlpatterns = [
    path("methods/", PaymentMethodListCreateAPIView.as_view()),
    path("methods/<int:pk>/", PaymentMethodDetailAPIView.as_view()),

    path("schedules/", PaymentScheduleListCreateAPIView.as_view()),
    path("schedules/<int:pk>/", PaymentScheduleDetailAPIView.as_view()),

    path("schedules/<int:pk>/receipt/", RentReceiptAPIView.as_view()),
    path("schedules/<int:pk>/receipt/share/", RentReceiptShareAPIView.as_view()),
    path("schedules/<int:pk>/receipt/email/", RentReceiptEmailAPIView.as_view()),

    path("rent-roll/", RentRollAPIView.as_view()),
    path("collect/", CollectRentAPIView.as_view()),
    path("reminders/", RentReminderListCreateAPIView.as_view()),
    path("reminders/preview/<int:pk>/", ReminderPreviewAPIView.as_view()),

    path("payments/", PaymentListCreateAPIView.as_view()),
    path("payments/<int:pk>/", PaymentDetailAPIView.as_view()),
    path("payments/<int:pk>/allocate/", PaymentAllocateAPIView.as_view()),
    path("payments/<int:pk>/cancel/", PaymentCancelAPIView.as_view()),
    path("payments/<int:pk>/receipt/", PaymentReceiptAPIView.as_view()),
    path("payments/<int:pk>/receipt/share/", PaymentReceiptShareAPIView.as_view()),
    path("payments/<int:pk>/receipt/email/", PaymentReceiptEmailAPIView.as_view()),
]
