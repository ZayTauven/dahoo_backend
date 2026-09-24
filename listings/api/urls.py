from django.urls import path
from .views import (
	ListingListCreateAPIView,
	ListingDetailAPIView,
	ListingPhotoDetailAPIView,
	ListingPhotoListCreateAPIView,
	ListingPublishAPIView,
	ListingUnpublishAPIView,
	ProspectInterestCreateAPIView,
	ProspectInterestListAPIView,
)

urlpatterns = [
	path("", ListingListCreateAPIView.as_view()),
	path("<int:pk>/", ListingDetailAPIView.as_view()),
	path("<int:pk>/publish/", ListingPublishAPIView.as_view()),
	path("<int:pk>/unpublish/", ListingUnpublishAPIView.as_view()),
	path("<int:pk>/photos/", ListingPhotoListCreateAPIView.as_view()),
	path("photos/<int:pk>/", ListingPhotoDetailAPIView.as_view()),
	# Ancienne route publique, conservée : même logique que /api/v1/public/listings/<id>/interest/.
	path("<int:pk>/interest/", ProspectInterestCreateAPIView.as_view()),
	path("<int:pk>/interests/", ProspectInterestListAPIView.as_view()),
]
