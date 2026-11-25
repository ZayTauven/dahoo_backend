from django.urls import path

from .views import (
    ExpenseDetailAPIView,
    ExpenseListCreateAPIView,
    OwnerDetailAPIView,
    OwnerListCreateAPIView,
    OwnerPayoutCancelAPIView,
    OwnerPayoutListCreateAPIView,
    OwnerStatementAPIView,
    OwnerStatementEmailAPIView,
    OwnerStatementPdfAPIView,
    OwnerStatementShareAPIView,
)

urlpatterns = [
    path("", OwnerListCreateAPIView.as_view()),
    path("<int:pk>/", OwnerDetailAPIView.as_view()),
    path("<int:pk>/statement/", OwnerStatementAPIView.as_view()),
    path("<int:pk>/statement/pdf/", OwnerStatementPdfAPIView.as_view()),
    path("<int:pk>/statement/share/", OwnerStatementShareAPIView.as_view()),
    path("<int:pk>/statement/email/", OwnerStatementEmailAPIView.as_view()),
    path("expenses/", ExpenseListCreateAPIView.as_view()),
    path("expenses/<int:pk>/", ExpenseDetailAPIView.as_view()),
    path("payouts/", OwnerPayoutListCreateAPIView.as_view()),
    path("payouts/<int:pk>/cancel/", OwnerPayoutCancelAPIView.as_view()),
]
