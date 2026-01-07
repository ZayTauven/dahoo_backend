from django.db import models
from django.conf import settings
from properties.models import Unit

User = settings.AUTH_USER_MODEL


# Modèle pour les catégories de maintenance
# ex : "PLUMBING", "ELECTRICAL", "CLEANING", etc.
class MaintenanceCategory(models.Model):
    code = models.CharField(max_length=50, unique=True)
    label = models.CharField(max_length=100)

    def __str__(self):
        return self.label


# Modèle pour les tickets de maintenance
# Chaque ticket est lié à une unité et à une catégorie de maintenance
class MaintenanceTicket(models.Model):
    PRIORITY_CHOICES = [
        ("LOW", "Basse"),
        ("MEDIUM", "Moyenne"),
        ("HIGH", "Haute"),
        ("URGENT", "Urgent"),
    ]

    STATUS_CHOICES = [
        ("OPEN", "Ouvert"),
        ("IN_PROGRESS", "En cours"),
        ("WAITING", "En attente"),
        ("RESOLVED", "Résolu"),
        ("CLOSED", "Clôturé"),
    ]

    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="maintenance_tickets")
    category = models.ForeignKey(MaintenanceCategory, on_delete=models.SET_NULL, null=True)

    reported_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="reported_tickets"
    )

    description = models.TextField()
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default="MEDIUM")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="OPEN")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


# Modèle pour les affectations de tickets de maintenance
# Chaque affectation lie un ticket à un intervenant
class MaintenanceAssignment(models.Model):
    ticket = models.ForeignKey(
        MaintenanceTicket,
        on_delete=models.CASCADE,
        related_name="assignments"
    )

    assigned_to = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="maintenance_assignments"
    )

    assigned_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="maintenance_assignments_created"
    )

    assigned_at = models.DateTimeField(auto_now_add=True)



# Modèle pour les journaux de maintenance
# Chaque journal est lié à un ticket de maintenance
class MaintenanceLog(models.Model):
    ticket = models.ForeignKey(
        MaintenanceTicket,
        on_delete=models.CASCADE,
        related_name="logs"
    )

    user = models.ForeignKey(User, on_delete=models.PROTECT)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)


