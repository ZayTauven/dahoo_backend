from django.urls import path

from .views import (
    DepositBoardAPIView,
    SettlementCancelAPIView,
    SettlementEmailAPIView,
    SettlementPdfAPIView,
    SettlementShareAPIView,
)

urlpatterns = [
    path("", DepositBoardAPIView.as_view()),
    path("settlements/<int:pk>/cancel/", SettlementCancelAPIView.as_view()),
    path("settlements/<int:pk>/pdf/", SettlementPdfAPIView.as_view()),
    path("settlements/<int:pk>/share/", SettlementShareAPIView.as_view()),
    path("settlements/<int:pk>/email/", SettlementEmailAPIView.as_view()),
]
