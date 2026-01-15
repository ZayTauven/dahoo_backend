from rest_framework import serializers
from analytics.models import BuildingKPI, FinancialSnapshot, Insight


class BuildingKPISerializer(serializers.ModelSerializer):
    class Meta:
        model = BuildingKPI
        fields = ["id", "building", "period_start", "period_end", "occupancy_rate", "expected_rent", "collected_rent", "incidents_count", "created_at"]


class FinancialSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = FinancialSnapshot
        fields = ["id", "owner", "month", "total_income", "total_expenses", "net_result"]


class InsightSerializer(serializers.ModelSerializer):
    class Meta:
        model = Insight
        fields = ["id", "target_type", "target_id", "insight_type", "score", "explanation", "created_at"]
