from django.db import models
from django.conf import settings
from properties.models import Unit

User = settings.AUTH_USER_MODEL

# Modèle abstrait pour les contrats de location et de vente
# Chaque contrat appartient à une organisation, est lié à une unité et garde son auteur
# Le type de contrat peut être "LEASE" (location) ou "SALE" (vente)
# Le statut du contrat peut être "DRAFT", "ACTIVE", "TERMINATED", "COMPLETED", ou "CANCELLED"

class Contract(models.Model):
    STATUS_CHOICES = [
        ("DRAFT", "Brouillon"),
        ("ACTIVE", "Actif"),
        ("TERMINATED", "Résilié"),
        ("COMPLETED", "Terminé"),
        ("CANCELLED", "Annulé"),
    ]

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="DRAFT"
    )

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="%(class)ss"
    )

    unit = models.ForeignKey(Unit, on_delete=models.PROTECT)

    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="%(class)s_created"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    signed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True



# Modèle pour les contrats de location
# Hérite du modèle abstrait Contract
class LeaseContract(Contract):
    tenant = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="lease_contracts"
    )

    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)

    rent_amount = models.DecimalField(max_digits=12, decimal_places=2)
    charges_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    deposit_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    payment_frequency = models.CharField(
        max_length=20,
        choices=[
            ("MONTHLY", "Mensuel"),
            ("QUARTERLY", "Trimestriel")
        ],
        default="MONTHLY"
    )

# Modèle pour les contrats de vente
class SaleContract(Contract):
    buyer = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="purchase_contracts"
    )

    sale_price = models.DecimalField(max_digits=15, decimal_places=2)
    commission_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    agreed_date = models.DateField()
    transfer_date = models.DateField(null=True, blank=True)


# Fiche locataire propre à une organisation.
# L'identité saisie (nom, email, pièce...) appartient à l'organisation : une autre agence qui
# enregistre le même numéro crée sa propre fiche et ne voit jamais celle-ci.
# `user` est le compte unique associé au téléphone (servira à l'espace locataire).
class Tenant(models.Model):
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="tenants"
    )
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="tenant_profiles")

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(blank=True)
    id_document_number = models.CharField(max_length=50, blank=True, help_text="CNI, passeport...")
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization", "user"], name="unique_tenant_per_organization"),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"
