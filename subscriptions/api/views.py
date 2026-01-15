from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404

from users.api.permissions import HasCapability
from subscriptions.models import SubscriptionPlan, Subscription, SubscriptionPayment
from .serializers import (
	SubscriptionPlanSerializer,
	SubscriptionSerializer,
	SubscriptionCreateSerializer,
	SubscriptionPaymentSerializer,
)


class SubscriptionPlanListCreateAPIView(generics.ListCreateAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "subscription.plan.view"
	queryset = SubscriptionPlan.objects.all()
	serializer_class = SubscriptionPlanSerializer


class SubscriptionPlanDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "subscription.plan.view"
	queryset = SubscriptionPlan.objects.all()
	serializer_class = SubscriptionPlanSerializer


class SubscriptionListCreateAPIView(generics.ListCreateAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "subscription.view"

	def get_queryset(self):
		return Subscription.objects.filter(owner=self.request.user)

	def get_serializer_class(self):
		if self.request.method == "POST":
			return SubscriptionCreateSerializer
		return SubscriptionSerializer

	def perform_create(self, serializer):
		serializer.save(owner=self.request.user)


class SubscriptionDetailAPIView(generics.RetrieveAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "subscription.view"
	queryset = Subscription.objects.all()
	serializer_class = SubscriptionSerializer


class SubscriptionPaymentListAPIView(generics.ListAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "subscription.payment.view"
	serializer_class = SubscriptionPaymentSerializer

	def get_queryset(self):
		return SubscriptionPayment.objects.filter(subscription__owner=self.request.user)

