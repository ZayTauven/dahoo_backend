"""Espace plateforme : offres, suivi des abonnements et règlements encaissés par l'équipe Dahoo."""

from django.db import transaction
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from access.permissions import IsPlatformAdmin
from documents.http import pdf_response
from organizations.models import Organization
from subscriptions.billing import (
    billing_reminder, billing_summary, build_billing_board, build_quote, cancel_payment, record_payment,
)
from subscriptions.documents import subscription_receipt
from subscriptions.models import BillingSettings, PlanRequest, SubscriptionPayment, SubscriptionPlan

from .serializers import (
    BillingBoardSerializer,
    BillingReminderSerializer,
    BillingSettingsSerializer,
    BillingSummarySerializer,
    CancelSubscriptionPaymentSerializer,
    PlanRequestSerializer,
    PlatformPlanSerializer,
    QuoteTermsSerializer,
    QuoteSerializer,
    RecordPaymentSerializer,
    SubscriptionPaymentSerializer,
)

PAYMENTS = SubscriptionPayment.objects.select_related("subscription__organization", "method")


class PlanWriteMixin:
    permission_classes = [IsPlatformAdmin]
    serializer_class = PlatformPlanSerializer
    queryset = SubscriptionPlan.objects.prefetch_related("subscriptions").order_by("-active", "price", "id")

    @transaction.atomic
    def save_plan(self, serializer):
        # Une seule offre borne l'essai : la dernière choisie.
        if serializer.validated_data.get("limits_trial"):
            SubscriptionPlan.objects.filter(limits_trial=True).exclude(pk=getattr(serializer.instance, "pk", None)).update(limits_trial=False)
        serializer.save()

    perform_create = perform_update = lambda self, serializer: self.save_plan(serializer)


class PlatformPlanListCreateAPIView(PlanWriteMixin, generics.ListCreateAPIView):
    pagination_class = None


class PlatformPlanDetailAPIView(PlanWriteMixin, generics.RetrieveUpdateDestroyAPIView):
    def perform_destroy(self, plan):
        try:
            plan.delete()
        except ProtectedError:
            raise ValidationError({"detail": "Cette offre a déjà été souscrite : retirez-la de la vente plutôt que de la supprimer."})


class PlatformBillingSettingsAPIView(generics.RetrieveUpdateAPIView):
    """Façon de régler (affichée aux clients) et mentions légales des reçus."""

    permission_classes = [IsPlatformAdmin]
    serializer_class = BillingSettingsSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        return BillingSettings.load()


class PlatformBillingBoardAPIView(APIView):
    """Suivi des abonnements : indicateurs, puis une ligne par client."""

    permission_classes = [IsPlatformAdmin]

    @extend_schema(responses=BillingBoardSerializer)
    def get(self, request):
        return Response(BillingBoardSerializer(build_billing_board()).data)


class OrganizationBillingAPIView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get_organization(self):
        return get_object_or_404(Organization, pk=self.kwargs["pk"])


class PlatformOrganizationBillingAPIView(OrganizationBillingAPIView):
    @extend_schema(responses=BillingSummarySerializer)
    def get(self, request, pk):
        return Response(BillingSummarySerializer(billing_summary(self.get_organization())).data)


class PlatformBillingQuoteAPIView(OrganizationBillingAPIView):
    """Ce que le règlement couvrira, sans rien enregistrer."""

    @extend_schema(request=QuoteTermsSerializer, responses=QuoteSerializer)
    def post(self, request, pk):
        serializer = QuoteTermsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(QuoteSerializer(build_quote(self.get_organization(), **serializer.validated_data)).data)


class PlatformRecordPaymentAPIView(OrganizationBillingAPIView):
    @extend_schema(request=RecordPaymentSerializer, responses={201: SubscriptionPaymentSerializer})
    def post(self, request, pk):
        serializer = RecordPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = record_payment(self.get_organization(), user=request.user, **serializer.validated_data)
        return Response(SubscriptionPaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


class PlatformBillingReminderAPIView(OrganizationBillingAPIView):
    @extend_schema(responses=BillingReminderSerializer)
    def get(self, request, pk):
        return Response(BillingReminderSerializer(billing_reminder(self.get_organization())).data)


class PlatformSubscriptionPaymentListAPIView(generics.ListAPIView):
    """Règlements reçus, annulés compris (filtre ?organization=)."""

    permission_classes = [IsPlatformAdmin]
    serializer_class = SubscriptionPaymentSerializer
    queryset = PAYMENTS.order_by("-paid_on", "-id")
    filterset_fields = {"subscription__organization": ["exact"]}
    search_fields = ["subscription__organization__name", "reference", "plan_name"]


class PlatformSubscriptionPaymentReceiptAPIView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    def get(self, request, pk):
        return pdf_response(subscription_receipt(get_object_or_404(PAYMENTS, pk=pk)))


class PlatformSubscriptionPaymentCancelAPIView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(request=CancelSubscriptionPaymentSerializer, responses=SubscriptionPaymentSerializer)
    def post(self, request, pk):
        serializer = CancelSubscriptionPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = cancel_payment(get_object_or_404(PAYMENTS, pk=pk), user=request.user, reason=serializer.validated_data["reason"])
        return Response(SubscriptionPaymentSerializer(payment).data)


class PlatformPlanRequestHandleAPIView(APIView):
    """Classer une demande d'offre sans règlement (client rappelé, demande abandonnée)."""

    permission_classes = [IsPlatformAdmin]

    @extend_schema(request=None, responses=PlanRequestSerializer)
    def post(self, request, pk):
        plan_request = get_object_or_404(PlanRequest, pk=pk)
        if plan_request.status == "OPEN":
            plan_request.status, plan_request.handled_at = "HANDLED", timezone.now()
            plan_request.save(update_fields=["status", "handled_at"])
        return Response(PlanRequestSerializer(plan_request).data)
