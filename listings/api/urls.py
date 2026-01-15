from django.urls import path
from .views import (
	ListingListCreateAPIView,
	ListingDetailAPIView,
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
	path("<int:pk>/interest/", ProspectInterestCreateAPIView.as_view()),
	path("<int:pk>/interests/", ProspectInterestListAPIView.as_view()),
]
