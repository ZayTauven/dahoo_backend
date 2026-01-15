from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404

from users.api.permissions import HasCapability
from access.models import Role, Capability, RoleCapability, UserRole, UserCapability
from .serializers import (
	RoleSerializer,
	CapabilitySerializer,
	RoleCapabilitySerializer,
	UserRoleSerializer,
	UserCapabilitySerializer,
)


class RoleListCreateAPIView(generics.ListCreateAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "access.role.view"
	queryset = Role.objects.all()
	serializer_class = RoleSerializer


class RoleDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "access.role.view"
	queryset = Role.objects.all()
	serializer_class = RoleSerializer


class CapabilityListCreateAPIView(generics.ListCreateAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "access.capability.view"
	queryset = Capability.objects.all()
	serializer_class = CapabilitySerializer


class UserRoleListCreateAPIView(generics.ListCreateAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "access.userrole.view"
	queryset = UserRole.objects.all()
	serializer_class = UserRoleSerializer


class UserCapabilityListCreateAPIView(generics.ListCreateAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "access.usercapability.view"
	queryset = UserCapability.objects.all()
	serializer_class = UserCapabilitySerializer

