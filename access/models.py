from django.db import models
from django.conf import settings

User = settings.AUTH_USER_MODEL


class Role(models.Model):
    code = models.CharField(max_length=50, unique=True)
    label = models.CharField(max_length=100)

    def __str__(self):
        return self.code


class Capability(models.Model):
    code = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.code


class RoleCapability(models.Model):
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    capability = models.ForeignKey(Capability, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("role", "capability")


class UserRole(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    active = models.BooleanField(default=True)


class UserCapability(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    capability = models.ForeignKey(Capability, on_delete=models.CASCADE)

    context_type = models.CharField(max_length=50)
    context_id = models.PositiveIntegerField()

    class Meta:
        indexes = [
            models.Index(fields=["context_type", "context_id"]),
        ]


