from django.db import models


# Create your models here.
class SubscriptionPlan(models.Model):
    BILLING_TYPE = [
        ("MONTHLY", "Mensuel"),
        ("YEARLY", "Annuel"),
        ("COMMISSION", "Commission"),
    ]

    name = models.CharField(max_length=100)
    billing_type = models.CharField(max_length=20, choices=BILLING_TYPE)

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )

    commission_rate = models.FloatField(
        null=True,
        blank=True,
        help_text="Pourcentage sur loyers ou ventes"
    )

    max_properties = models.PositiveIntegerField(null=True, blank=True)
    max_units = models.PositiveIntegerField(null=True, blank=True)
    max_users = models.PositiveIntegerField(null=True, blank=True)

    active = models.BooleanField(default=True)


class Subscription(models.Model):
    STATUS = [
        ("ACTIVE", "Actif"),
        ("SUSPENDED", "Suspendu"),
        ("EXPIRED", "Expiré"),
    ]

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="subscriptions"
    )

    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT
    )

    status = models.CharField(max_length=20, choices=STATUS, default="ACTIVE")

    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)


class SubscriptionPayment(models.Model):
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.CASCADE,
        related_name="payments"
    )

    payment = models.OneToOneField(
        "payments.Payment",
        on_delete=models.CASCADE
    )

