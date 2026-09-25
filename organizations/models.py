from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

User = settings.AUTH_USER_MODEL


def default_trial_end():
    return timezone.now() + timedelta(days=settings.TRIAL_DAYS)


# Une organisation est le client de Dahoo (agence, syndic, gestionnaire...).
# Toutes les données métier lui appartiennent et sont cloisonnées par organisation.
# Un propriétaire indépendant est simplement une organisation d'une seule personne.
class Organization(models.Model):
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    # Logo affiché sur le portail public (annuaire, fiche agence, annonces).
    logo = models.ImageField(upload_to="organizations/logos/", blank=True)

    is_active = models.BooleanField(default=True)
    # Organisation interne de Dahoo (l'éditeur utilise aussi l'application comme une agence) :
    # jamais soumise à l'essai ni à l'abonnement.
    is_internal = models.BooleanField(default=False)
    # Fin de la période d'essai : au-delà, sans abonnement actif, l'accès passe en lecture seule.
    trial_ends_at = models.DateTimeField(default=default_trial_end)
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
