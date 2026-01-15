from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone

from users.api.permissions import HasCapability
from listings.models import Listing, Prospect, ProspectInterest
from .serializers import (
	ListingSerializer,
	ListingCreateSerializer,
	ProspectSerializer,
	ProspectInterestSerializer,
)


class ListingListCreateAPIView(generics.ListCreateAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "listing.view"
	queryset = Listing.objects.all()
	serializer_class = ListingSerializer

	def get_queryset(self):
		# basic owner filter — show listings created by the user
		return Listing.objects.filter(created_by=self.request.user)

	def get_serializer_class(self):
		if self.request.method == "POST":
			return ListingCreateSerializer
		return ListingSerializer

	def perform_create(self, serializer):
		serializer.save(created_by=self.request.user)


class ListingDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "listing.view"
	queryset = Listing.objects.all()
	serializer_class = ListingSerializer

	def get_object(self):
		return get_object_or_404(Listing, pk=self.kwargs.get("pk"), created_by=self.request.user)


class ListingPublishAPIView(APIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "listing.publish"

	def post(self, request, pk):
		listing = get_object_or_404(Listing, pk=pk, created_by=request.user)
		listing.status = "PUBLISHED"
		listing.published_at = timezone.now()
		listing.save()
		return Response(ListingSerializer(listing).data)


class ListingUnpublishAPIView(APIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "listing.unpublish"

	def post(self, request, pk):
		listing = get_object_or_404(Listing, pk=pk, created_by=request.user)
		listing.status = "SUSPENDED"
		listing.save()
		return Response(ListingSerializer(listing).data)


class ProspectInterestCreateAPIView(APIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "listing.interest"

	def post(self, request, pk):
		listing = get_object_or_404(Listing, pk=pk)
		serializer = ProspectInterestSerializer(data=request.data, context={"listing": listing})
		serializer.is_valid(raise_exception=True)
		interest = serializer.save()
		return Response(ProspectInterestSerializer(interest).data, status=status.HTTP_201_CREATED)


class ProspectInterestListAPIView(generics.ListAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "listing.view"

	serializer_class = ProspectInterestSerializer

	def get_queryset(self):
		listing = get_object_or_404(Listing, pk=self.kwargs.get("pk"))
		return ProspectInterest.objects.filter(listing=listing)

