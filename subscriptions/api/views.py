from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from access.permissions import IsStaffOrReadOnly
from documents.http import pdf_response
from organizations.scoping import OrganizationScopedMixin
from subscriptions.billing import billing_summary, request_plan
from subscriptions.documents import subscription_receipt
from subscriptions.models import BillingSettings, Subscription, SubscriptionPayment, SubscriptionPlan

from .serializers import (
	PlanRequestCreateSerializer,
	PlanRequestSerializer,
	SubscriptionOverviewSerializer,
	SubscriptionPaymentSerializer,
	SubscriptionPlanSerializer,
	SubscriptionSerializer,
)


# Catalogue des offres : lisible par tous, géré par l'équipe Dahoo dans l'espace plateforme.
class SubscriptionPlanListAPIView(generics.ListAPIView):
	permission_classes = [IsStaffOrReadOnly]
	queryset = SubscriptionPlan.objects.order_by("price", "id")
	serializer_class = SubscriptionPlanSerializer
	pagination_class = None

	def get_queryset(self):
		queryset = super().get_queryset()
		return queryset if self.request.user.is_staff else queryset.filter(active=True)


# L'abonnement d'une organisation est ouvert par l'équipe Dahoo, après paiement :
# l'API l'expose en lecture seule pour éviter qu'un client s'attribue lui-même une offre.
class SubscriptionListAPIView(OrganizationScopedMixin, generics.ListAPIView):
	required_capability = "subscription.view"
	queryset = Subscription.objects.select_related("plan").order_by("-start_date", "-id")
	serializer_class = SubscriptionSerializer


class SubscriptionDetailAPIView(OrganizationScopedMixin, generics.RetrieveAPIView):
	required_capability = "subscription.view"
	queryset = Subscription.objects.select_related("plan")
	serializer_class = SubscriptionSerializer


class SubscriptionOverviewAPIView(OrganizationScopedMixin, APIView):
	"""Abonnement en cours, consommation, offres proposées et façon de régler."""

	required_capability = "subscription.view"

	@extend_schema(responses=SubscriptionOverviewSerializer)
	def get(self, request):
		plans = SubscriptionPlan.objects.filter(active=True, audience__in=["ALL", self.organization.kind]).order_by("price", "id")
		data = {
			**billing_summary(self.organization),
			"plans": plans,
			"payment_instructions": BillingSettings.load().payment_instructions,
		}
		return Response(SubscriptionOverviewSerializer(data).data)


class SubscriptionPaymentListAPIView(OrganizationScopedMixin, generics.ListAPIView):
	required_capability = "subscription.view"
	organization_lookup = "subscription__organization"
	queryset = SubscriptionPayment.objects.valid().select_related("subscription__organization", "method")
	serializer_class = SubscriptionPaymentSerializer


class SubscriptionPaymentReceiptAPIView(OrganizationScopedMixin, APIView):
	required_capability = "subscription.view"

	@extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
	def get(self, request, pk):
		payments = SubscriptionPayment.objects.select_related("subscription__organization", "method")
		return pdf_response(subscription_receipt(get_object_or_404(payments, pk=pk, subscription__organization=self.organization)))


class PlanRequestCreateAPIView(OrganizationScopedMixin, APIView):
	"""Demander une offre : possible même quand l'espace est en lecture seule."""

	required_capability = "organization.update"
	allowed_without_subscription = True

	@extend_schema(request=PlanRequestCreateSerializer, responses={201: PlanRequestSerializer})
	def post(self, request):
		serializer = PlanRequestCreateSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		plan = serializer.validated_data["plan"]
		if plan.audience not in ("ALL", self.organization.kind):
			raise ValidationError({"plan": "Cette offre ne correspond pas à votre espace."})
		created = request_plan(self.organization, user=request.user, plan=plan, message=serializer.validated_data.get("message", ""))
		return Response(PlanRequestSerializer(created).data, status=status.HTTP_201_CREATED)
