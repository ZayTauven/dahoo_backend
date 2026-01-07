from django.db import models
from django.conf import settings
from properties.models import Unit

User = settings.AUTH_USER_MODEL

# Modèle abstrait pour les contrats de location et de vente
# Chaque contrat est lié à une unité et à un propriétaire
# Le type de contrat peut être "LEASE" (location) ou "SALE" (vente)
# Le statut du contrat peut être "DRAFT", "ACTIVE", "TERMINATED", "COMPLETED", ou "CANCELLED"

class Contract(models.Model):
    CONTRACT_TYPE_CHOICES = [
        ("LEASE", "Location"),
        ("SALE", "Vente"),
    ]

    STATUS_CHOICES = [
        ("DRAFT", "Brouillon"),
        ("ACTIVE", "Actif"),
        ("TERMINATED", "Résilié"),
        ("COMPLETED", "Terminé"),
        ("CANCELLED", "Annulé"),
    ]

    contract_type = models.CharField(max_length=10, choices=CONTRACT_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="DRAFT")

    unit = models.ForeignKey(Unit, on_delete=models.PROTECT)
    owner = models.ForeignKey(User, on_delete=models.PROTECT)

    created_at = models.DateTimeField(auto_now_add=True)
    signed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True


# Modèle pour les contrats de location
# Hérite du modèle abstrait Contract
class LeaseContract(Contract):
    tenant = models.ForeignKey(User, on_delete=models.PROTECT, related_name="leases")

    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)

    rent_amount = models.DecimalField(max_digits=12, decimal_places=2)
    charges_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    deposit_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    owner = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="lease_contracts"
    )
    tenant = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="leases"
    )

    payment_frequency = models.CharField(
        max_length=20,
        choices=[("MONTHLY", "Mensuel"), ("QUARTERLY", "Trimestriel")],
        default="MONTHLY"
    )


# Modèle pour les contrats de vente
class SaleContract(Contract):
    buyer = models.ForeignKey(User, on_delete=models.PROTECT, related_name="purchases")

    sale_price = models.DecimalField(max_digits=15, decimal_places=2)
    commission_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    owner = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="sale_contracts"
    )
    buyer = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="purchases"
    )

    agreed_date = models.DateField()
    transfer_date = models.DateField(null=True, blank=True)

