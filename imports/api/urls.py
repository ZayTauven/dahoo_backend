from django.urls import path

from .views import ImportCommitAPIView, ImportPreviewAPIView, ImportTemplateAPIView

urlpatterns = [
    path("template/", ImportTemplateAPIView.as_view()),
    path("preview/", ImportPreviewAPIView.as_view()),
    path("commit/", ImportCommitAPIView.as_view()),
]
