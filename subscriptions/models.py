from django.conf import settings
from django.db import models
from django.utils import timezone

User = settings.AUTH_USER_MODEL

ENDING_DAYS = 7


# Offre vendue par Dahoo. Son prix est figé sur chaque abonnement : le modifier ne change rien aux abonnés.
class SubscriptionPlan(models.Model):
    BILLING_TYPE = [
        ("MONTHLY", "Mensuel"),
        ("YEARLY", "Annuel"),
        ("COMMISSION", "Commission"),
    ]
    AUDIENCES = [
        ("ALL", "Agences et propriétaires"),
        ("AGENCY", "Agences"),
        ("OWNER", "Propriétaires"),
    ]

    name = models.CharField(max_length=100)
    description = models.CharField(max_length=160, blank=True)
    audience = models.CharField(max_length=10, choices=AUDIENCES, default="ALL")
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
    # Ses limites s'appliquent aussi pendant l'essai (une offre au plus ; aucune : essai sans limite de volume).
    limits_trial = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["limits_trial"], condition=models.Q(limits_trial=True), name="one_plan_limits_trial"
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def months(self):
        """Durée d'une échéance : un an, sinon un mois (une commission se règle au mois)."""
        return 12 if self.billing_type == "YEARLY" else 1


class Subscription(models.Model):
    STATUS = [
        ("ACTIVE", "Actif"),
        ("SUSPENDED", "Suspendu"),
        ("EXPIRED", "Expiré"),
    ]
    # État lisible, déduit du statut et des dates.
    STATES = [
        ("ACTIVE", "Actif"),
        ("ENDING", "Se termine bientôt"),
        ("UPCOMING", "À venir"),
        ("ENDED", "Terminé"),
        ("SUSPENDED", "Suspendu"),
    ]

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="subscriptions"
    )

    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT,
        related_name="subscriptions"
    )

    status = models.CharField(max_length=20, choices=STATUS, default="ACTIVE")
    # Prix convenu, repris de l'offre à l'attribution (modifiable : remise durable, ancien tarif).
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    start_date = models.DateField()
    # Payé jusqu'à cette date ; vide : sans échéance (accès offert ou convenu).
    end_date = models.DateField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.organization} · {self.plan}"

    def save(self, *args, **kwargs):
        if self._state.adding and self.price is None:
            self.price = self.plan.price
        super().save(*args, **kwargs)

    @property
    def state(self):
        today = timezone.localdate()
        if self.status == "SUSPENDED":
            return "SUSPENDED"
        if self.status == "EXPIRED" or (self.end_date and self.end_date < today):
            return "ENDED"
        if self.start_date > today:
            return "UPCOMING"
        if self.end_date and (self.end_date - today).days <= ENDING_DAYS:
            return "ENDING"
        return "ACTIVE"

    @property
    def days_left(self):
        return None if self.end_date is None else (self.end_date - timezone.localdate()).days


class SubscriptionPaymentQuerySet(models.QuerySet):
    def valid(self):
        return self.filter(cancelled_at__isnull=True)


# Règlement d'un abonnement, reçu hors ligne par Dahoo. Comme un paiement : ne se modifie pas, s'annule.
class SubscriptionPayment(models.Model):
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.PROTECT,
        related_name="payments"
    )
    # Offre et prix au jour du règlement : le reçu ne change pas si l'offre est renommée.
    plan_name = models.CharField(max_length=100)
    months = models.PositiveSmallIntegerField()
    quantity = models.PositiveSmallIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    credit = models.DecimalField("reste de l'offre précédente", max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField("remise", max_digits=12, decimal_places=2, default=0)
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    period_start = models.DateField()
    period_end = models.DateField()

    paid_on = models.DateField(default=timezone.localdate)
    method = models.ForeignKey("payments.PaymentMethod", on_delete=models.PROTECT, related_name="+")
    reference = models.CharField(max_length=100, blank=True)
    note = models.CharField(max_length=200, blank=True)

    # De quoi revenir à l'état précédent si ce règlement est annulé.
    opens_subscription = models.BooleanField(default=False)
    previous_end_date = models.DateField(null=True, blank=True)
    replaced_subscription = models.ForeignKey(
        Subscription, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    replaced_end_date = models.DateField(null=True, blank=True)

    recorded_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    cancel_reason = models.CharField(max_length=200, blank=True)

    objects = SubscriptionPaymentQuerySet.as_manager()

    class Meta:
        ordering = ["-paid_on", "-id"]

    def __str__(self):
        return self.number

    @property
    def number(self):
        return f"AB{self.paid_on:%Y}-{self.pk:04d}"


# Une agence demande une offre depuis son espace ; l'équipe Dahoo l'appelle puis enregistre le règlement.
class PlanRequest(models.Model):
    STATUS = [
        ("OPEN", "À traiter"),
        ("HANDLED", "Traitée"),
    ]

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="plan_requests"
    )
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.CASCADE, related_name="requests")
    requested_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="+")
    message = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="OPEN")
    created_at = models.DateTimeField(auto_now_add=True)
    handled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization"], condition=models.Q(status="OPEN"), name="one_open_plan_request"
            ),
        ]


# Réglages de facturation de Dahoo, saisis par l'équipe (une seule ligne).
class BillingSettings(models.Model):
    # Ex. « Wave ou Orange Money au ..., en indiquant le nom de l'agence ».
    payment_instructions = models.TextField(blank=True)
    # Mentions légales des reçus (NINEA, registre du commerce...).
    legal_notice = models.TextField(blank=True)

    @classmethod
    def load(cls):
        return cls.objects.get_or_create(pk=1)[0]
