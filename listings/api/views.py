from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from listings.models import Listing, ProspectInterest
from organizations.scoping import OrganizationScopedMixin

from .serializers import ListingSerializer, ProspectInterestSerializer, PublicInterestSerializer

LISTING_ORGANIZATION = "unit__building__property__organization"


class ListingListCreateAPIView(OrganizationScopedMixin, generics.ListCreateAPIView):
	capability_resource = "listing"
	organization_lookup = LISTING_ORGANIZATION
	queryset = Listing.objects.order_by("-created_at")
	serializer_class = ListingSerializer

	def perform_create(self, serializer):
		serializer.save(created_by=self.request.user)


class ListingDetailAPIView(OrganizationScopedMixin, generics.RetrieveUpdateDestroyAPIView):
	capability_resource = "listing"
	organization_lookup = LISTING_ORGANIZATION
	queryset = Listing.objects.all()
	serializer_class = ListingSerializer


class ListingStatusAPIView(OrganizationScopedMixin, APIView):
	allowed_from = ()
	target_status = None

	def apply(self, listing):
		listing.status = self.target_status

	@extend_schema(request=None, responses=ListingSerializer)
	def post(self, request, pk):
		listing = get_object_or_404(Listing, pk=pk, **{LISTING_ORGANIZATION: self.organization})
		if listing.status not in self.allowed_from:
			raise ValidationError({"status": f"Action impossible depuis le statut {listing.get_status_display()}."})
		self.apply(listing)
		listing.save(update_fields=["status", "published_at"])
		return Response(ListingSerializer(listing, context={"request": request}).data)


class ListingPublishAPIView(ListingStatusAPIView):
	required_capability = "listing.publish"
	allowed_from = ("DRAFT", "SUSPENDED")
	target_status = "PUBLISHED"

	def apply(self, listing):
		super().apply(listing)
		listing.published_at = timezone.now()


class ListingUnpublishAPIView(ListingStatusAPIView):
	required_capability = "listing.unpublish"
	allowed_from = ("PUBLISHED",)
	target_status = "SUSPENDED"


class ProspectInterestCreateAPIView(APIView):
	"""Déclaration d'intérêt publique (site vitrine) sur une annonce publiée."""

	permission_classes = [AllowAny]
	authentication_classes = []
	throttle_scope = "public_interest"

	@extend_schema(request=ProspectInterestSerializer, responses={201: dict})
	def post(self, request, pk):
		listing = get_object_or_404(Listing.objects.select_related("unit__building__property"), pk=pk, status="PUBLISHED")
		serializer = PublicInterestSerializer(data=request.data, context={"listing": listing})
		serializer.is_valid(raise_exception=True)
		interest = serializer.save()
		return Response(serializer.to_representation(interest), status=status.HTTP_201_CREATED)


class ProspectInterestListAPIView(OrganizationScopedMixin, generics.ListAPIView):
	required_capability = "listing.interest.view"
	organization_lookup = "listing__" + LISTING_ORGANIZATION
	queryset = ProspectInterest.objects.select_related("prospect").order_by("-created_at")
	serializer_class = ProspectInterestSerializer

	def get_queryset(self):
		listing = get_object_or_404(Listing, pk=self.kwargs["pk"], **{LISTING_ORGANIZATION: self.organization})
		return super().get_queryset().filter(listing=listing)
