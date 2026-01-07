from django.db import models
from django.conf import settings
from properties.models import Building

User = settings.AUTH_USER_MODEL

# Ce n’est pas un rôle, c’est un profil opérationnel.
class GuardianProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    buildings = models.ManyToManyField(Building, related_name="guardians")

    shift_start = models.TimeField()
    shift_end = models.TimeField()

    active = models.BooleanField(default=True)


# Modèle pour les événements de terrain
class FieldEvent(models.Model):
    EVENT_TYPE = [
        ("ENTRY_EXIT", "Entrée / Sortie"),
        ("VISIT", "Visite"),
        ("DELIVERY", "Livraison"),
        ("INCIDENT", "Incident"),
        ("ANOMALY", "Anomalie"),
    ]

    building = models.ForeignKey(Building, on_delete=models.CASCADE)
    unit = models.ForeignKey(
        "properties.Unit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    recorded_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="field_events"
    )

    event_type = models.CharField(max_length=20, choices=EVENT_TYPE)

    description = models.TextField()
    occurred_at = models.DateTimeField()

    created_at = models.DateTimeField(auto_now_add=True)


# Modèle pour les événements de visite
class VisitEvent(models.Model):
    field_event = models.OneToOneField(FieldEvent, on_delete=models.CASCADE)

    visitor_name = models.CharField(max_length=150)
    purpose = models.CharField(max_length=200)

    authorized_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="authorized_visits"
    )

# Modèle pour les événements de livraison
class DeliveryEvent(models.Model):
    field_event = models.OneToOneField(FieldEvent, on_delete=models.CASCADE)

    company = models.CharField(max_length=150)
    package_count = models.PositiveIntegerField(default=1)

    recipient = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )


