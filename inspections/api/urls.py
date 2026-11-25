from django.urls import path

from .views import (
    InspectionDetailAPIView,
    InspectionItemCreateAPIView,
    InspectionItemDetailAPIView,
    InspectionPdfAPIView,
    InspectionPhotoCreateAPIView,
    InspectionPhotoDeleteAPIView,
    InspectionPhotoFileAPIView,
    InspectionReopenAPIView,
    InspectionShareAPIView,
    InspectionSignAPIView,
)

urlpatterns = [
    path("<int:pk>/", InspectionDetailAPIView.as_view()),
    path("<int:pk>/items/", InspectionItemCreateAPIView.as_view()),
    path("<int:pk>/photos/", InspectionPhotoCreateAPIView.as_view()),
    path("<int:pk>/sign/", InspectionSignAPIView.as_view()),
    path("<int:pk>/reopen/", InspectionReopenAPIView.as_view()),
    path("<int:pk>/pdf/", InspectionPdfAPIView.as_view()),
    path("<int:pk>/share/", InspectionShareAPIView.as_view()),
    path("items/<int:pk>/", InspectionItemDetailAPIView.as_view()),
    path("photos/<int:pk>/", InspectionPhotoDeleteAPIView.as_view()),
    path("photos/file/<str:token>/", InspectionPhotoFileAPIView.as_view()),
]
