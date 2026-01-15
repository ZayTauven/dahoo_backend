from django.urls import path
from .views import (
    GuardianProfileListCreateAPIView,
    GuardianProfileDetailAPIView,
    FieldEventListCreateAPIView,
    FieldEventDetailAPIView,
    VisitEventDetailAPIView,
    DeliveryEventDetailAPIView,
)

urlpatterns = [
    path("guardians/", GuardianProfileListCreateAPIView.as_view()),
    path("guardians/<int:pk>/", GuardianProfileDetailAPIView.as_view()),

    path("events/", FieldEventListCreateAPIView.as_view()),
    path("events/<int:pk>/", FieldEventDetailAPIView.as_view()),
    path("visits/<int:pk>/", VisitEventDetailAPIView.as_view()),
    path("deliveries/<int:pk>/", DeliveryEventDetailAPIView.as_view()),
]
