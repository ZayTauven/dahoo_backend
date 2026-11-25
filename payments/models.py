from django.db import models
from django.utils import timezone
from django.conf import settings
from leases.models import LeaseContract, SaleContract

User = settings.AUTH_USER_MODEL

# Loyers soldés par la caution à la sortie (deposits) : écrit par Dahoo, jamais choisi à l'encaissement.
DEPOSIT_METHOD = "DEPOSIT"


# Modèle pour les méthodes de paiement
# ex : "WAVE", "ORANGE_MONEY", "BANK_TRANSFER", "CASH", etc.
class PaymentMethod(models.Model):
    code = models.CharField(max_length=50, unique=True)
    label = models.CharField(max_length=100)

    def __str__(self):
        return self.label

# Modèle pour les échéanciers de paiement
# Chaque échéancier est lié soit à un contrat de location, soit à un contrat de vente
class PaymentSchedule(models.Model):
    SCHEDULE_TYPE_CHOICES = [
        ("RENT", "Loyer"),
        ("CHARGE", "Charge"),
        ("SALE", "Vente"),
        ("DEPOSIT", "Caution"),
        # Dette antérieure à Dahoo, reprise à l'import : encaissable, sans quittance (plusieurs mois mêlés).
        ("ARREARS", "Arriéré repris"),
    ]

    lease_contract = models.ForeignKey(
        LeaseContract,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="schedules"
    )

    sale_contract = models.ForeignKey(
        SaleContract,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="schedules"
    )

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="payment_schedules"
    )

    schedule_type = models.CharField(max_length=20, choices=SCHEDULE_TYPE_CHOICES)

    due_date = models.DateField()
    amount_due = models.DecimalField(max_digits=12, decimal_places=2)

    is_paid = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(lease_contract__isnull=False, sale_contract__isnull=True)
                    | models.Q(lease_contract__isnull=True, sale_contract__isnull=False)
                ),
                name="schedule_linked_to_exactly_one_contract",
            ),
        ]


class PaymentQuerySet(models.QuerySet):
    def valid(self):
        """Paiements non annulés : les seuls à compter dans les totaux."""
        return self.filter(cancelled_at__isnull=True)

    def cash(self):
        """Argent réellement entré : une retenue sur caution est un loyer réglé, mais l'argent était déjà là."""
        return self.valid().exclude(payment_method__code=DEPOSIT_METHOD)


# Modèle pour les paiements effectués
# Chaque paiement est lié à une méthode de paiement
# payer = qui a payé (locataire, acquéreur) ; recorded_by = le membre qui l'a saisi
class Payment(models.Model):
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="payments"
    )
    payer = models.ForeignKey(User, on_delete=models.PROTECT)
    recorded_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="recorded_payments")
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2)

    payment_method = models.ForeignKey(PaymentMethod, on_delete=models.PROTECT)
    # Date réelle de l'encaissement (saisissable : un paiement peut être enregistré le lendemain).
    payment_date = models.DateTimeField(default=timezone.now)

    reference = models.CharField(max_length=100, blank=True, null=True)
    note = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    # Un paiement ne se supprime pas : saisi par erreur, il s'annule avec un motif.
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="cancelled_payments")
    cancel_reason = models.CharField(max_length=200, blank=True)

    objects = PaymentQuerySet.as_manager()


# Modèle pour l'allocation des paiements aux échéanciers
# Permet de lier un paiement à un ou plusieurs échéanciers
class PaymentAllocation(models.Model):
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="allocations")
    # RESTRICT : une échéance réglée ne disparaît pas, sauf avec toute l'organisation.
    schedule = models.ForeignKey(PaymentSchedule, on_delete=models.RESTRICT, related_name="allocations")

    allocated_amount = models.DecimalField(max_digits=12, decimal_places=2)
    # Commission de l'agence (%) au jour de l'encaissement, figée (voir Property.commission_rate).
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)


# Relance d'un locataire en retard, préparée par Dahoo et envoyée par l'agence (WhatsApp, appel...).
class RentReminder(models.Model):
    CHANNELS = [
        ("WHATSAPP", "WhatsApp"),
        ("SMS", "SMS"),
        ("CALL", "Appel"),
        ("EMAIL", "E-mail"),
    ]

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="rent_reminders"
    )
    lease = models.ForeignKey(LeaseContract, on_delete=models.CASCADE, related_name="reminders")
    channel = models.CharField(max_length=20, choices=CHANNELS, default="WHATSAPP")
    amount = models.DecimalField("montant dû à la relance", max_digits=12, decimal_places=2)
    message = models.TextField(blank=True)
    # Vide pour une relance automatique.
    sent_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="sent_reminders")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
