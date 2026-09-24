from django.db import transaction
from django.db.models import Max
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import SAFE_METHODS, AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle
from rest_framework.views import APIView

from listings.models import Listing, ListingPhoto, ProspectInterest
from listings.photos import MAX_PHOTOS_PER_LISTING, with_cover
from organizations.scoping import OrganizationScopedMixin
from public.visibility import public_listings

from .serializers import (
	ListingPhotoSerializer,
	ListingPhotoUpdateSerializer,
	ListingSerializer,
	ProspectInterestSerializer,
	PublicInterestReceiptSerializer,
	PublicInterestSerializer,
)

LISTING_ORGANIZATION = "unit__building__property__organization"


def listings_with_details():
	"""Annonces avec libellé du lot, couverture et nombre de photos, sans requête par ligne."""
	return with_cover(Listing.objects.select_related("unit__building__property"), count=True)


class ListingListCreateAPIView(OrganizationScopedMixin, generics.ListCreateAPIView):
	capability_resource = "listing"
	organization_lookup = LISTING_ORGANIZATION
	queryset = listings_with_details().order_by("-created_at")
	serializer_class = ListingSerializer
	filterset_fields = ["status", "listing_type"]
	search_fields = ["title", "description"]
	ordering_fields = ["created_at", "published_at", "price"]

	def perform_create(self, serializer):
		serializer.save(created_by=self.request.user)


class ListingDetailAPIView(OrganizationScopedMixin, generics.RetrieveUpdateDestroyAPIView):
	capability_resource = "listing"
	organization_lookup = LISTING_ORGANIZATION
	queryset = listings_with_details()
	serializer_class = ListingSerializer


class ListingStatusAPIView(OrganizationScopedMixin, APIView):
	allowed_from = ()
	target_status = None

	def apply(self, listing):
		listing.status = self.target_status

	@extend_schema(request=None, responses=ListingSerializer)
	def post(self, request, pk):
		listing = get_object_or_404(listings_with_details(), pk=pk, **{LISTING_ORGANIZATION: self.organization})
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


class ListingPhotoCapabilityMixin(OrganizationScopedMixin):
	# Les photos font partie de l'annonce : lecture = listing.view, toute écriture = listing.update.
	@property
	def required_capability(self):
		return "listing.view" if self.request.method in SAFE_METHODS else "listing.update"


class ListingPhotoListCreateAPIView(ListingPhotoCapabilityMixin, generics.ListCreateAPIView):
	"""Photos d'une annonce (ordre d'affichage) ; ajout par envoi multipart du fichier `image`."""

	organization_lookup = "listing__" + LISTING_ORGANIZATION
	queryset = ListingPhoto.objects.all()
	serializer_class = ListingPhotoSerializer
	parser_classes = [MultiPartParser, FormParser]
	pagination_class = None

	def get_listing(self, lock=False):
		queryset = Listing.objects.select_for_update(of=("self",)) if lock else Listing.objects.all()
		return get_object_or_404(queryset, pk=self.kwargs["pk"], **{LISTING_ORGANIZATION: self.organization})

	def get_queryset(self):
		return super().get_queryset().filter(listing=self.get_listing())

	@transaction.atomic
	def perform_create(self, serializer):
		# Verrou sur l'annonce : deux envois simultanés ne peuvent pas dépasser la limite.
		listing = self.get_listing(lock=True)
		photos = ListingPhoto.objects.filter(listing=listing)
		if photos.count() >= MAX_PHOTOS_PER_LISTING:
			raise ValidationError({"image": f"{MAX_PHOTOS_PER_LISTING} photos maximum par annonce."})
		position = serializer.validated_data.get("position")
		if position is None:
			last = photos.aggregate(last=Max("position"))["last"]
			position = 0 if last is None else last + 1
		serializer.save(listing=listing, position=position)


class ListingPhotoDetailAPIView(ListingPhotoCapabilityMixin, generics.RetrieveUpdateDestroyAPIView):
	"""Modifier le texte alternatif ou la position d'une photo, ou la supprimer."""

	organization_lookup = "listing__" + LISTING_ORGANIZATION
	queryset = ListingPhoto.objects.all()
	serializer_class = ListingPhotoUpdateSerializer
	http_method_names = ["get", "patch", "delete", "head", "options"]


class ProspectInterestCreateAPIView(APIView):
	"""Déclaration d'intérêt publique (site vitrine) sur une annonce visible du public."""

	permission_classes = [AllowAny]
	authentication_classes = []
	throttle_classes = [AnonRateThrottle, ScopedRateThrottle]
	throttle_scope = "public_interest"

	def get_listing(self, pk):
		return get_object_or_404(public_listings().select_related("unit__building__property"), pk=pk)

	@extend_schema(request=ProspectInterestSerializer, responses={201: PublicInterestReceiptSerializer})
	def post(self, request, pk):
		listing = self.get_listing(pk)
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
