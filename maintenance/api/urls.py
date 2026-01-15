from django.urls import path
from .views import (
	MaintenanceCategoryListCreateAPIView,
	MaintenanceCategoryDetailAPIView,
	MaintenanceTicketListCreateAPIView,
	MaintenanceTicketDetailAPIView,
	MaintenanceTicketChangeStatusAPIView,
	MaintenanceTicketAssignAPIView,
	MaintenanceLogListCreateAPIView,
)

urlpatterns = [
	path("categories/", MaintenanceCategoryListCreateAPIView.as_view()),
	path("categories/<int:pk>/", MaintenanceCategoryDetailAPIView.as_view()),

	path("tickets/", MaintenanceTicketListCreateAPIView.as_view()),
	path("tickets/<int:pk>/", MaintenanceTicketDetailAPIView.as_view()),
	path("tickets/<int:pk>/status/", MaintenanceTicketChangeStatusAPIView.as_view()),
	path("tickets/<int:pk>/assign/", MaintenanceTicketAssignAPIView.as_view()),

	path("tickets/<int:pk>/logs/", MaintenanceLogListCreateAPIView.as_view()),
]
