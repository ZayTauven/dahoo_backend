from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from rest_framework.permissions import BasePermission

class Capability(models.Model):
    code = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

def get_user_capabilities(user):
        return list(
            user.capabilities.filter(active=True)
            .values_list("code", flat=True)
        )


class HasCapability(BasePermission):
    required_capability = None

    def has_permission(self, request, view):
        if not self.required_capability:
            return True
        return self.required_capability in get_user_capabilities(request.user)



