from rest_framework import generics

from access.permissions import IsStaffOrReadOnly
from organizations.scoping import OrganizationScopedMixin
from subscriptions.models import Subscription, SubscriptionPayment, SubscriptionPlan

from .serializers import (
	SubscriptionPaymentSerializer,
	SubscriptionPlanSerializer,
	SubscriptionSerializer,
)


# Catalogue des offres : lisible par tous, géré par le staff Dahoo.
class SubscriptionPlanListCreateAPIView(generics.ListCreateAPIView):
	permission_classes = [IsStaffOrReadOnly]
	queryset = SubscriptionPlan.objects.order_by("price")
	serializer_class = SubscriptionPlanSerializer
	pagination_class = None

	def get_queryset(self):
		queryset = super().get_queryset()
		return queryset if self.request.user.is_staff else queryset.filter(active=True)


class SubscriptionPlanDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
	permission_classes = [IsStaffOrReadOnly]
	queryset = SubscriptionPlan.objects.all()
	serializer_class = SubscriptionPlanSerializer


# L'abonnement d'une organisation est attribué par le staff Dahoo (admin), après paiement :
# l'API l'expose en lecture seule pour éviter qu'un client s'attribue lui-même une offre.
class SubscriptionListAPIView(OrganizationScopedMixin, generics.ListAPIView):
	required_capability = "subscription.view"
	queryset = Subscription.objects.select_related("plan").order_by("-start_date")
	serializer_class = SubscriptionSerializer


class SubscriptionDetailAPIView(OrganizationScopedMixin, generics.RetrieveAPIView):
	required_capability = "subscription.view"
	queryset = Subscription.objects.select_related("plan")
	serializer_class = SubscriptionSerializer


class SubscriptionPaymentListAPIView(OrganizationScopedMixin, generics.ListAPIView):
	required_capability = "subscription.view"
	organization_lookup = "subscription__organization"
	queryset = SubscriptionPayment.objects.order_by("-id")
	serializer_class = SubscriptionPaymentSerializer
