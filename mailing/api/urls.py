from django.urls import path

from .views import OptOutAPIView

urlpatterns = [path("opt-out/", OptOutAPIView.as_view())]
