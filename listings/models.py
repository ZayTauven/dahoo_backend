from django.db import models
from properties.models import Unit
from django.conf import settings

User = settings.AUTH_USER_MODEL

#Une Unit peut avoir :
#plusieurs annonces dans le temps
#une seule active à la fois (règle métier plus tard) 
#Chaque annonce est créée par un user (agent immobilier, propriétaire, gestionnaire...)

class Listing(models.Model):
    LISTING_TYPE = [
        ("RENT", "Location"),
        ("SALE", "Vente"),
    ]

    STATUS = [
        ("DRAFT", "Brouillon"),
        ("PUBLISHED", "Publié"),
        ("SUSPENDED", "Suspendu"),
        ("CLOSED", "Clôturé"),
    ]

    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="listings")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)

    title = models.CharField(max_length=200)
    description = models.TextField()

    listing_type = models.CharField(max_length=10, choices=LISTING_TYPE)
    price = models.DecimalField(max_digits=12, decimal_places=2)

    status = models.CharField(max_length=20, choices=STATUS, default="DRAFT")

    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


# Le prospect peut exister sans user au départ
# Puis être lié à un user lors de la conversion

class Prospect(models.Model):
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30)
    email = models.EmailField(blank=True, null=True)

    source = models.CharField(
        max_length=50,
        help_text="site, whatsapp, agent, facebook..."
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.full_name

# Modèle pour enregistrer l'intérêt d'un prospect pour une annonce
# Un prospect peut : s’intéresser à plusieurs annonces / être recontacté plus tard

class ProspectInterest(models.Model):
    listing = models.ForeignKey(
        Listing,
        on_delete=models.CASCADE,
        related_name="interests"
    )

    prospect = models.ForeignKey(
        Prospect,
        on_delete=models.CASCADE,
        related_name="interests"
    )

    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


#Cette table est fondamentale : elle garde la trace du parcours, elle permet des stats commerciales,elle évite toute ambiguïté
# Modèle pour enregistrer la conversion d'un prospect en locataire ou propriétaire

class ProspectConversion(models.Model):
    CONVERSION_TYPE = [
        ("TENANT", "Locataire"),
        ("OWNER", "Propriétaire"),
    ]

    prospect = models.OneToOneField(Prospect, on_delete=models.CASCADE)
    conversion_type = models.CharField(max_length=20, choices=CONVERSION_TYPE)

    user = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        help_text="User créé ou associé après conversion"
    )

    converted_at = models.DateTimeField(auto_now_add=True)
