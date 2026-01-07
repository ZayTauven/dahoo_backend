from django.db import models
from django.conf import settings


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

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
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



def can_create_unit(user):
    sub = Subscription.objects.filter(
        owner=user,
        status="ACTIVE"
    ).select_related("plan").first()

    if not sub or not sub.plan.max_units:
        return False

    return user.units.count() < sub.plan.max_units
