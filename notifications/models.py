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
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    body = models.TextField()

    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

