from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from rest_framework.permissions import BasePermission

from access.models import RoleCapability, UserRole

class Capability(models.Model):
    code = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)


def get_user_capabilities(user):
    roles = UserRole.objects.filter(
    user=user,
    active=True
    ).values_list("role_id", flat=True)

    capabilities = RoleCapability.objects.filter(
        role_id__in=roles
    ).values_list("capability__code", flat=True)

    return set(capabilities)


class HasCapability(BasePermission):
    required_capability = None

    def has_permission(self, request, view):
        if not self.required_capability:
            return True
        return self.required_capability in get_user_capabilities(request.user)



