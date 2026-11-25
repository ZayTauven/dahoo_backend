from django.conf import settings
from django.db import models
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class DepositSettlementQuerySet(models.QuerySet):
    def valid(self):
        return self.filter(cancelled_at__isnull=True)


# Décompte de caution à la fin d'un bail : ce qui est retenu, ce qui est rendu. S'annule avec un motif.
class DepositSettlement(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="deposit_settlements")
    lease = models.ForeignKey("leases.LeaseContract", on_delete=models.PROTECT, related_name="deposit_settlements")

    held_amount = models.DecimalField("caution détenue", max_digits=12, decimal_places=2)
    refund_amount = models.DecimalField("montant rendu", max_digits=12, decimal_places=2)
    settled_on = models.DateField(default=timezone.localdate)
    # Vide quand rien n'est rendu.
    method = models.ForeignKey("payments.PaymentMethod", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    reference = models.CharField(max_length=100, blank=True)
    note = models.CharField(max_length=300, blank=True)

    # Loyers soldés par la caution : un vrai paiement, pour que quittances et relevés restent justes.
    rent_payment = models.OneToOneField("payments.Payment", on_delete=models.PROTECT, null=True, blank=True, related_name="deposit_settlement")
    # Caution versée en partie : son échéance est ramenée au montant reçu ; ceci permet d'annuler.
    deposit_due_before = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    recorded_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    cancel_reason = models.CharField(max_length=200, blank=True)

    objects = DepositSettlementQuerySet.as_manager()

    class Meta:
        ordering = ["-settled_on", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["lease"], condition=models.Q(cancelled_at__isnull=True), name="one_valid_settlement_per_lease"),
        ]

    @property
    def number(self):
        return f"C{self.settled_on:%Y%m}-{self.pk}"


class DepositDeduction(models.Model):
    KINDS = [
        ("REPAIR", "Réparation"),
        ("CLEANING", "Nettoyage"),
        ("UTILITIES", "Eau et électricité"),
        ("KEYS", "Clés et badges"),
        ("OTHER", "Autre"),
    ]

    settlement = models.ForeignKey(DepositSettlement, on_delete=models.CASCADE, related_name="deductions")
    kind = models.CharField(max_length=20, choices=KINDS, default="REPAIR")
    label = models.CharField(max_length=150)
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["id"]
