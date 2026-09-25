from django.db import models
from django.conf import settings

User = settings.AUTH_USER_MODEL


class Notification(models.Model):
    CHANNELS = [
        ("EMAIL", "Email"),
        ("SMS", "SMS"),
        ("WHATSAPP", "WhatsApp"),
        ("IN_APP", "In App"),
    ]

    STATUS = [
        ("PENDING", "Pending"),
        ("SENT", "Sent"),
        ("FAILED", "Failed"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")

    channel = models.CharField(max_length=20, choices=CHANNELS)
    subject = models.CharField(max_length=200, blank=True)
    message = models.TextField()

    status = models.CharField(max_length=20, choices=STATUS, default="PENDING")

    scheduled_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)


class NotificationTemplate(models.Model):
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="notification_templates"
    )

    EVENT_TYPES = [
        ("RENT_DUE", "Loyer dû"),
        ("PAYMENT_RECEIVED", "Paiement reçu"),
        ("INCIDENT_REPORTED", "Incident signalé"),
        ("VISIT_SCHEDULED", "Visite programmée"),
        ("PROSPECT_FOLLOWUP", "Relance prospect"),
    ]

    event_type = models.CharField(max_length=50, choices=EVENT_TYPES)
    channel = models.CharField(max_length=20)

    subject_template = models.CharField(max_length=200)
    body_template = models.TextField()

    active = models.BooleanField(default=True)



class AutomationRule(models.Model):
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="automation_rules"
    )

    EVENT = [
        ("LEASE_CREATED", "Contrat créé"),
        ("RENT_DUE", "Loyer à échéance"),
        ("PAYMENT_LATE", "Paiement en retard"),
        ("INCIDENT_CREATED", "Incident déclaré"),
        ("PROSPECT_CREATED", "Prospect créé"),
    ]

    event = models.CharField(max_length=50, choices=EVENT)

    active = models.BooleanField(default=True)

    delay_minutes = models.PositiveIntegerField(default=0)
    channel = models.CharField(max_length=20)

    template = models.ForeignKey(
        NotificationTemplate,
        on_delete=models.PROTECT
    )


class InAppNotification(models.Model):
    """
    Notification affichée dans l'espace connecté (cloche de l'en-tête). Créée par le serveur
    (notifications/services.py), jamais via l'API. `organization` vide = notification de la plateforme.
    """

    KINDS = [
        ("VISIT_REQUEST", "Demande de visite"),
        ("PAYMENT_RECEIVED", "Paiement enregistré"),
        ("TICKET_CREATED", "Ticket de maintenance"),
        ("TICKET_ASSIGNED", "Ticket assigné"),
        ("RENT_OVERDUE", "Loyer en retard"),
        ("LEASE_ENDING", "Bail arrivant à échéance"),
        ("TRIAL_ENDING", "Fin d'essai"),
        ("DEMO_REQUEST", "Demande de démo"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="inapp_notifications")
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, null=True, blank=True, related_name="inapp_notifications"
    )
    kind = models.CharField(max_length=30, choices=KINDS)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    # Chemin de l'écran concerné dans le front (« /espace/maintenance/12 »).
    link = models.CharField(max_length=300, blank=True)
    # Rappels calculés (retards, fins de bail...) : une seule notification par utilisateur et par clé.
    dedupe_key = models.CharField(max_length=120, blank=True)

    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["user", "read"])]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "dedupe_key"], condition=~models.Q(dedupe_key=""), name="inapp_unique_dedupe_per_user"
            )
        ]

