from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from deposits.documents import settlement_report, share_settlement
from deposits.models import DepositSettlement
from deposits.services import build_deposits, cancel_settlement, deposit_summary, settle_deposit
from documents.http import pdf_response
from leases.models import LeaseContract
from mailing.agency import email_deposit_settlement
from organizations.scoping import OrganizationScopedMixin
from payments.api.serializers import ShareLinkSerializer

from .serializers import (
    CancelSettlementSerializer,
    DepositBoardSerializer,
    DepositSettlementSerializer,
    DepositSummarySerializer,
    SettleDepositSerializer,
)

SETTLEMENTS = DepositSettlement.objects.select_related(
    "organization", "method", "rent_payment", "lease__tenant", "lease__unit__building__property"
).prefetch_related("deductions")


class DepositBoardAPIView(OrganizationScopedMixin, APIView):
    """Cautions de l'agence : ce qu'elle détient, ce qu'elle doit rendre."""

    required_capability = "deposit.view"

    @extend_schema(responses=DepositBoardSerializer)
    def get(self, request):
        return Response(DepositBoardSerializer(build_deposits(self.organization)).data)


class LeaseDepositAPIView(OrganizationScopedMixin, APIView):
    required_capability = "deposit.view"

    @extend_schema(responses=DepositSummarySerializer)
    def get(self, request, pk):
        lease = get_object_or_404(LeaseContract, pk=pk, organization=self.organization)
        return Response(DepositSummarySerializer(deposit_summary(lease)).data)


class SettleDepositAPIView(OrganizationScopedMixin, APIView):
    """Décompte : retenues, puis ce qui est rendu au locataire."""

    required_capability = "deposit.settle"

    @extend_schema(request=SettleDepositSerializer, responses={201: DepositSettlementSerializer})
    def post(self, request, pk):
        lease = get_object_or_404(LeaseContract, pk=pk, organization=self.organization)
        serializer = SettleDepositSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        settlement = settle_deposit(lease, user=request.user, **serializer.validated_data)
        return Response(DepositSettlementSerializer(settlement).data, status=status.HTTP_201_CREATED)


class SettlementMixin(OrganizationScopedMixin):
    required_capability = "deposit.view"

    def get_settlement(self, pk):
        return get_object_or_404(SETTLEMENTS, pk=pk, organization=self.organization)


class SettlementCancelAPIView(SettlementMixin, APIView):
    required_capability = "deposit.cancel"

    @extend_schema(request=CancelSettlementSerializer, responses=DepositSettlementSerializer)
    def post(self, request, pk):
        serializer = CancelSettlementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        settlement = cancel_settlement(self.get_settlement(pk), user=request.user, reason=serializer.validated_data["reason"])
        return Response(DepositSettlementSerializer(settlement).data)


class SettlementPdfAPIView(SettlementMixin, APIView):
    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    def get(self, request, pk):
        return pdf_response(settlement_report(self.get_settlement(pk)))


class SettlementShareAPIView(SettlementMixin, APIView):
    @extend_schema(responses=ShareLinkSerializer)
    def get(self, request, pk):
        return Response(ShareLinkSerializer(share_settlement(self.get_settlement(pk))).data)


class SettlementEmailAPIView(SettlementMixin, APIView):
    required_capability = "deposit.settle"
    throttle_scope = "email_send"

    @extend_schema(request=None, responses={204: None})
    def post(self, request, pk):
        email_deposit_settlement(self.get_settlement(pk))
        return Response(status=status.HTTP_204_NO_CONTENT)
