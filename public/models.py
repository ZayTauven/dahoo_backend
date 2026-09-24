from django.db import models


# Demande de démo envoyée depuis la vitrine SaaS par une agence intéressée.
# Traitée par l'équipe Dahoo depuis l'espace plateforme ou l'admin Django.
class DemoRequest(models.Model):
    UNITS_RANGE = [
        ("1-20", "1-20"),
        ("21-100", "21-100"),
        ("101-500", "101-500"),
        ("500+", "500+"),
    ]

    agency_name = models.CharField(max_length=200)
    contact_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30)
    email = models.EmailField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    units_range = models.CharField("nombre de lots gérés", max_length=10, choices=UNITS_RANGE)
    message = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    handled = models.BooleanField("traitée", default=False)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "demande de démo"
        verbose_name_plural = "demandes de démo"

    def __str__(self):
        return f"{self.agency_name} ({self.contact_name})"
