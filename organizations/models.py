from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL


# Une organisation est le client de Dahoo (agence, syndic, gestionnaire...).
# Toutes les données métier lui appartiennent et sont cloisonnées par organisation.
# Un propriétaire indépendant est simplement une organisation d'une seule personne.
class Organization(models.Model):
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


# Appartenance d'un utilisateur à une organisation, avec son rôle dans celle-ci.
# Un même utilisateur peut être membre de plusieurs organisations avec des rôles différents.
class Membership(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="memberships")
    role = models.ForeignKey("access.Role", on_delete=models.PROTECT, related_name="memberships")

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "organization"], name="unique_membership_per_organization"),
        ]

    def __str__(self):
        return f"{self.user} @ {self.organization} ({self.role})"
