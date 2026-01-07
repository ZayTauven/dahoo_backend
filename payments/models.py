from django.db import models
from django.conf import settings
from leases.models import LeaseContract, SaleContract

User = settings.AUTH_USER_MODEL

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

    schedule_type = models.CharField(max_length=20, choices=SCHEDULE_TYPE_CHOICES)

    due_date = models.DateField()
    amount_due = models.DecimalField(max_digits=12, decimal_places=2)

    is_paid = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)


# Modèle pour les paiements effectués
# Chaque paiement est lié à une méthode de paiement
class Payment(models.Model):
    payer = models.ForeignKey(User, on_delete=models.PROTECT)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2)

    payment_method = models.ForeignKey(PaymentMethod, on_delete=models.PROTECT)
    payment_date = models.DateTimeField(auto_now_add=True)

    reference = models.CharField(max_length=100, blank=True, null=True)
    note = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)


# Modèle pour l'allocation des paiements aux échéanciers
# Permet de lier un paiement à un ou plusieurs échéanciers
class PaymentAllocation(models.Model):
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="allocations")
    schedule = models.ForeignKey(PaymentSchedule, on_delete=models.CASCADE, related_name="allocations")

    allocated_amount = models.DecimalField(max_digits=12, decimal_places=2)

    created_at = models.DateTimeField(auto_now_add=True)




    

