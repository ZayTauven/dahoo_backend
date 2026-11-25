from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Property(models.Model):
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="properties"
    )
    name = models.CharField(max_length=255)
    # Bailleur pour le compte duquel le bien est géré ; vide si l'organisation en est propriétaire.
    owner = models.ForeignKey(
        "owners.Owner", on_delete=models.PROTECT, null=True, blank=True, related_name="properties"
    )
    # Mandat de gestion : commission de l'agence, en % des loyers encaissés. Le taux du jour est figé
    # sur chaque encaissement : le changer ne réécrit pas les relevés passés.
    commission_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    address = models.TextField()
    city = models.CharField(max_length=100)
    neighborhood = models.CharField("quartier", max_length=100, blank=True)
    # Position exacte du bien : jamais exposée telle quelle sur le portail public (arrondie).
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)


class Building(models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="buildings")
    name = models.CharField(max_length=255)


class Unit(models.Model):
    STATUS_CHOICES = [
        ("FREE", "Libre"),
        ("RENTED", "Loué"),
        ("MAINTENANCE", "Maintenance"),
        ("SOLD", "Vendu"),
    ]

    CATEGORY_CHOICES = [
        ("APARTMENT", "Appartement"),
        ("HOUSE", "Maison / villa"),
        ("STUDIO", "Studio"),
        ("OFFICE", "Bureau"),
        ("SHOP", "Local commercial"),
        ("LAND", "Terrain"),
    ]

    building = models.ForeignKey(Building, on_delete=models.CASCADE, related_name="units")
    reference = models.CharField(max_length=50)
    # Catégorie normalisée (filtres du portail) ; `unit_type` reste le libellé libre (T2, F3...).
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default="APARTMENT")
    unit_type = models.CharField(max_length=50)
    surface = models.FloatField()
    bedrooms = models.PositiveSmallIntegerField(null=True, blank=True)
    bathrooms = models.PositiveSmallIntegerField(null=True, blank=True)
    parking_spaces = models.PositiveSmallIntegerField(null=True, blank=True)
    is_furnished = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)

    @property
    def label(self):
        """« Résidence X · Bâtiment A · A101 » (prévoir select_related("building__property") en liste)."""
        return f"{self.building.property.name} · {self.building.name} · {self.reference}"
