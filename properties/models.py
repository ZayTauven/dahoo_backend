from django.db import models
from django.conf import settings

User = settings.AUTH_USER_MODEL


class Property(models.Model):
    name = models.CharField(max_length=255)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="owned_properties")
    address = models.TextField()
    city = models.CharField(max_length=100)

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

    building = models.ForeignKey(Building, on_delete=models.CASCADE, related_name="units")
    reference = models.CharField(max_length=50)
    unit_type = models.CharField(max_length=50)
    surface = models.FloatField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
