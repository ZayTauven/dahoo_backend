from django.conf import settings
from django.db import models
from django.utils import timezone

User = settings.AUTH_USER_MODEL


# Fiche bailleur (propriétaire) propre à une organisation, sur le modèle de la fiche locataire :
# l'identité saisie appartient à l'agence, `user` est le compte unique associé au téléphone
# (servira à l'espace bailleur).
class Owner(models.Model):
    PAYOUT_CHANNELS = [
        ("BANK_TRANSFER", "Virement"),
        ("WAVE", "Wave"),
        ("ORANGE_MONEY", "Orange Money"),
        ("CHEQUE", "Chèque"),
        ("CASH", "Espèces"),
    ]

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="owners")
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="owner_profiles")

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    # Comment le bailleur souhaite être réglé (« IBAN SN… », numéro Wave...).
    payout_channel = models.CharField(max_length=20, choices=PAYOUT_CHANNELS, default="BANK_TRANSFER")
    payout_details = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization", "user"], name="unique_owner_per_organization"),
        ]

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self):
        return self.full_name


# Dépense engagée pour un bien (réparation, taxe, eau...). Déduite du reversement au bailleur.
class Expense(models.Model):
    CATEGORIES = [
        ("REPAIR", "Travaux et réparations"),
        ("UTILITIES", "Eau et électricité"),
        ("STAFF", "Gardiennage et nettoyage"),
        ("TAX", "Impôts et taxes"),
        ("INSURANCE", "Assurance"),
        ("FEES", "Frais et honoraires"),
        ("OTHER", "Autre"),
    ]

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="expenses")
    property = models.ForeignKey("properties.Property", on_delete=models.PROTECT, related_name="expenses")
    unit = models.ForeignKey("properties.Unit", on_delete=models.PROTECT, null=True, blank=True, related_name="expenses")
    ticket = models.ForeignKey(
        "maintenance.MaintenanceTicket", on_delete=models.SET_NULL, null=True, blank=True, related_name="expenses"
    )

    category = models.CharField(max_length=20, choices=CATEGORIES, default="REPAIR")
    label = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    spent_on = models.DateField(default=timezone.localdate)
    note = models.TextField(blank=True)

    recorded_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="recorded_expenses")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-spent_on", "-id"]

    def __str__(self):
        return self.label


# Reversement au bailleur. Comme un paiement : ne se modifie pas, s'annule avec un motif.
class OwnerPayout(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="owner_payouts")
    owner = models.ForeignKey(Owner, on_delete=models.PROTECT, related_name="payouts")

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_on = models.DateField(default=timezone.localdate)
    channel = models.CharField(max_length=20, choices=Owner.PAYOUT_CHANNELS, default="BANK_TRANSFER")
    reference = models.CharField(max_length=100, blank=True)
    note = models.TextField(blank=True)

    recorded_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="recorded_payouts")
    created_at = models.DateTimeField(auto_now_add=True)

    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="cancelled_payouts")
    cancel_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-paid_on", "-id"]

    def __str__(self):
        return f"{self.owner} {self.amount}"
