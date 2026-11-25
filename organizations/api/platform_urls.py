from django.urls import path

from subscriptions.api.platform import (
    PlatformBillingBoardAPIView,
    PlatformBillingQuoteAPIView,
    PlatformBillingReminderAPIView,
    PlatformBillingSettingsAPIView,
    PlatformOrganizationBillingAPIView,
    PlatformPlanDetailAPIView,
    PlatformPlanListCreateAPIView,
    PlatformPlanRequestHandleAPIView,
    PlatformRecordPaymentAPIView,
    PlatformSubscriptionPaymentCancelAPIView,
    PlatformSubscriptionPaymentListAPIView,
    PlatformSubscriptionPaymentReceiptAPIView,
)

from .platform import (
    PlatformDashboardAPIView,
    PlatformDemoRequestDetailAPIView,
    PlatformDemoRequestListAPIView,
    PlatformMemberResetPasswordAPIView,
    PlatformOrganizationDetailAPIView,
    PlatformOrganizationListCreateAPIView,
    PlatformOrganizationMembersAPIView,
    PlatformSubscriptionDetailAPIView,
    PlatformSubscriptionListCreateAPIView,
)

urlpatterns = [
    path("dashboard/", PlatformDashboardAPIView.as_view()),
    path("organizations/", PlatformOrganizationListCreateAPIView.as_view()),
    path("organizations/<int:pk>/", PlatformOrganizationDetailAPIView.as_view()),
    path("organizations/<int:pk>/members/", PlatformOrganizationMembersAPIView.as_view()),
    path("organizations/<int:pk>/members/<int:member_pk>/reset-password/", PlatformMemberResetPasswordAPIView.as_view()),
    path("organizations/<int:pk>/subscriptions/", PlatformSubscriptionListCreateAPIView.as_view()),
    path("subscriptions/<int:pk>/", PlatformSubscriptionDetailAPIView.as_view()),
    path("plans/", PlatformPlanListCreateAPIView.as_view()),
    path("plans/<int:pk>/", PlatformPlanDetailAPIView.as_view()),
    path("billing/", PlatformBillingBoardAPIView.as_view()),
    path("billing/settings/", PlatformBillingSettingsAPIView.as_view()),
    path("organizations/<int:pk>/billing/", PlatformOrganizationBillingAPIView.as_view()),
    path("organizations/<int:pk>/billing/quote/", PlatformBillingQuoteAPIView.as_view()),
    path("organizations/<int:pk>/billing/payments/", PlatformRecordPaymentAPIView.as_view()),
    path("organizations/<int:pk>/billing/reminder/", PlatformBillingReminderAPIView.as_view()),
    path("subscription-payments/", PlatformSubscriptionPaymentListAPIView.as_view()),
    path("subscription-payments/<int:pk>/receipt/", PlatformSubscriptionPaymentReceiptAPIView.as_view()),
    path("subscription-payments/<int:pk>/cancel/", PlatformSubscriptionPaymentCancelAPIView.as_view()),
    path("plan-requests/<int:pk>/handle/", PlatformPlanRequestHandleAPIView.as_view()),
    path("demo-requests/", PlatformDemoRequestListAPIView.as_view()),
    path("demo-requests/<int:pk>/", PlatformDemoRequestDetailAPIView.as_view()),
]
