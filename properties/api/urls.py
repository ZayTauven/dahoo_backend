from django.urls import path
from .views import (
	PropertyListCreateAPIView,
	PropertyDetailAPIView,
	BuildingListCreateAPIView,
	BuildingDetailAPIView,
	UnitListCreateAPIView,
	UnitDetailAPIView,
	UnitChangeStatusAPIView,
)

urlpatterns = [
	path("properties/", PropertyListCreateAPIView.as_view()),
	path("properties/<int:pk>/", PropertyDetailAPIView.as_view()),

	path("properties/<int:property_pk>/buildings/", BuildingListCreateAPIView.as_view()),
	path("buildings/<int:pk>/", BuildingDetailAPIView.as_view()),

	path("buildings/<int:building_pk>/units/", UnitListCreateAPIView.as_view()),
	path("units/<int:pk>/", UnitDetailAPIView.as_view()),
	path("units/<int:pk>/status/", UnitChangeStatusAPIView.as_view()),
]
