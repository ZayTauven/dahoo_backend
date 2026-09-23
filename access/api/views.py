from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from access.models import Capability, Role

from .serializers import CapabilitySerializer, RoleSerializer


# Rôles et capabilities sont communs à toutes les organisations et gérés dans l'admin Django :
# l'API les expose en lecture pour que le front puisse les afficher et les attribuer.
class RoleListAPIView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    queryset = Role.objects.prefetch_related("capabilities").order_by("code")
    serializer_class = RoleSerializer


class CapabilityListAPIView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    queryset = Capability.objects.order_by("code")
    serializer_class = CapabilitySerializer
    pagination_class = None
