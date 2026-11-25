from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters import rest_framework as filters
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from documents.http import parse_month, pdf_response
from documents.receipts import owner_statement, share_statement
from mailing.agency import email_statement
from organizations.scoping import OrganizationScopedMixin
from owners.models import Expense, Owner, OwnerPayout
from owners.statements import build_statement, owner_balances
from payments.api.serializers import CancelSerializer, ShareLinkSerializer

from .serializers import ExpenseSerializer, OwnerPayoutSerializer, OwnerSerializer, StatementSerializer

MONTH_PARAMETER = OpenApiParameter("month", OpenApiTypes.STR, description="Mois « AAAA-MM », le mois courant par défaut.")


class OwnerQuerysetMixin(OrganizationScopedMixin):
    capability_resource = "owner"
    serializer_class = OwnerSerializer
    queryset = (
        Owner.objects.select_related("user")
        .annotate(
            properties_count=Count("properties", distinct=True),
            units_count=Count("properties__buildings__units", distinct=True),
        )
        .order_by("last_name", "first_name", "id")
    )
    search_fields = ["first_name", "last_name", "user__phone", "email"]
    ordering_fields = ["last_name", "created_at", "units_count"]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        organization = getattr(self.request, "organization", None)
        if organization is not None:
            context["balances"] = owner_balances(organization)
        return context


class OwnerListCreateAPIView(OwnerQuerysetMixin, generics.ListCreateAPIView):
    pass


class OwnerDetailAPIView(OwnerQuerysetMixin, generics.RetrieveUpdateDestroyAPIView):
    pass


class OwnerStatementMixin(OrganizationScopedMixin):
    required_capability = "owner.view"

    def get_owner(self, pk):
        return get_object_or_404(Owner.objects.select_related("organization", "user"), pk=pk, organization=self.organization)

    def get_month(self):
        return parse_month(self.request.query_params.get("month"))


class OwnerStatementAPIView(OwnerStatementMixin, APIView):
    """Relevé de gestion d'un mois : encaissements, commission, dépenses, reversements, solde."""

    @extend_schema(parameters=[MONTH_PARAMETER], responses=StatementSerializer)
    def get(self, request, pk):
        return Response(StatementSerializer(build_statement(self.get_owner(pk), month=self.get_month())).data)


class OwnerStatementPdfAPIView(OwnerStatementMixin, APIView):
    @extend_schema(parameters=[MONTH_PARAMETER], responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    def get(self, request, pk):
        return pdf_response(owner_statement(self.get_owner(pk), self.get_month()))


class OwnerStatementShareAPIView(OwnerStatementMixin, APIView):
    @extend_schema(parameters=[MONTH_PARAMETER], responses=ShareLinkSerializer)
    def get(self, request, pk):
        return Response(ShareLinkSerializer(share_statement(self.get_owner(pk), self.get_month())).data)


class OwnerStatementEmailAPIView(OwnerStatementMixin, APIView):
    """Envoie le relevé du mois par e-mail au bailleur."""

    required_capability = "owner.payout.create"
    throttle_scope = "email_send"

    @extend_schema(parameters=[MONTH_PARAMETER], request=None, responses={204: None})
    def post(self, request, pk):
        email_statement(self.get_owner(pk), self.get_month())
        return Response(status=status.HTTP_204_NO_CONTENT)


class ExpenseFilter(filters.FilterSet):
    property = filters.NumberFilter(field_name="property_id")
    owner = filters.NumberFilter(field_name="property__owner_id")
    ticket = filters.NumberFilter(field_name="ticket_id")
    spent_after = filters.DateFilter(field_name="spent_on", lookup_expr="gte")
    spent_before = filters.DateFilter(field_name="spent_on", lookup_expr="lte")

    class Meta:
        model = Expense
        fields = ["category", "property", "owner", "ticket", "spent_after", "spent_before"]


class ExpenseListCreateAPIView(OrganizationScopedMixin, generics.ListCreateAPIView):
    capability_resource = "expense"
    queryset = Expense.objects.select_related("property", "unit").order_by("-spent_on", "-id")
    serializer_class = ExpenseSerializer
    filterset_class = ExpenseFilter
    search_fields = ["label", "note"]
    ordering_fields = ["spent_on", "amount"]

    def perform_create(self, serializer):
        serializer.save(organization=self.organization, recorded_by=self.request.user)


class ExpenseDetailAPIView(OrganizationScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    capability_resource = "expense"
    queryset = Expense.objects.select_related("property", "unit")
    serializer_class = ExpenseSerializer


class OwnerPayoutListCreateAPIView(OrganizationScopedMixin, generics.ListCreateAPIView):
    capability_resource = "owner.payout"
    queryset = OwnerPayout.objects.select_related("owner").order_by("-paid_on", "-id")
    serializer_class = OwnerPayoutSerializer
    filterset_fields = ["owner"]
    ordering_fields = ["paid_on", "amount"]

    def perform_create(self, serializer):
        serializer.save(organization=self.organization, recorded_by=self.request.user)


class OwnerPayoutCancelAPIView(OrganizationScopedMixin, APIView):
    required_capability = "owner.payout.cancel"

    @extend_schema(request=CancelSerializer, responses=OwnerPayoutSerializer)
    def post(self, request, pk):
        payout = get_object_or_404(OwnerPayout, pk=pk, organization=self.organization)
        serializer = CancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if payout.cancelled_at:
            raise ValidationError({"detail": "Ce reversement est déjà annulé."})
        payout.cancelled_at, payout.cancelled_by = timezone.now(), request.user
        payout.cancel_reason = serializer.validated_data["reason"]
        payout.save(update_fields=["cancelled_at", "cancelled_by", "cancel_reason"])
        return Response(OwnerPayoutSerializer(payout, context={"request": request}).data)
