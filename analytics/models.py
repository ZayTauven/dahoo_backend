from django.db import models
from django.conf import settings

# Create your models here.
class BuildingKPI(models.Model):
    building = models.ForeignKey("properties.Building", on_delete=models.CASCADE)

    period_start = models.DateField()
    period_end = models.DateField()

    occupancy_rate = models.FloatField()
    expected_rent = models.DecimalField(max_digits=14, decimal_places=2)
    collected_rent = models.DecimalField(max_digits=14, decimal_places=2)

    incidents_count = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)


class FinancialSnapshot(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )

    month = models.DateField()
    total_income = models.DecimalField(max_digits=14, decimal_places=2)
    total_expenses = models.DecimalField(max_digits=14, decimal_places=2)
    net_result = models.DecimalField(max_digits=14, decimal_places=2)


class Insight(models.Model):
    INSIGHT_TYPE = [
        ("PAYMENT_RISK", "Risque d’impayé"),
        ("HIGH_VACANCY", "Vacance élevée"),
        ("MAINTENANCE_ALERT", "Maintenance excessive"),
        ("UNDERPRICED", "Bien sous-évalué"),
    ]

    target_type = models.CharField(max_length=50)
    target_id = models.PositiveIntegerField()

    insight_type = models.CharField(max_length=50, choices=INSIGHT_TYPE)
    score = models.FloatField()

    explanation = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
