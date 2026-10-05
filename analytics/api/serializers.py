from rest_framework import serializers

from analytics.models import BuildingKPI, FinancialSnapshot, Insight
from listings.models import Listing
from maintenance.models import MaintenanceTicket


# Types d'alertes du tableau de bord (nom d'enum figé dans ENUM_NAME_OVERRIDES).
INSIGHT_KINDS = ["overdue", "urgent_tickets", "leases_ending", "vacancy", "interests"]


class BuildingKPISerializer(serializers.ModelSerializer):
    class Meta:
        model = BuildingKPI
        fields = ["id", "building", "period_start", "period_end", "occupancy_rate", "expected_rent", "collected_rent", "incidents_count", "created_at"]


class FinancialSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = FinancialSnapshot
        fields = ["id", "month", "total_income", "total_expenses", "net_result"]


class InsightSerializer(serializers.ModelSerializer):
    class Meta:
        model = Insight
        fields = ["id", "target_type", "target_id", "insight_type", "score", "explanation", "created_at"]


# ── Tableau de bord de l'espace agence (analytics/dashboard.py) ──
# Sérialiseurs en lecture seule : ils décrivent la réponse pour le schéma OpenAPI (types du front).

MONEY = {"max_digits": 16, "decimal_places": 2}


class UnitCategoryCountSerializer(serializers.Serializer):
    category = serializers.CharField()
    label = serializers.CharField()
    count = serializers.IntegerField()


class UnitsByStatusSerializer(serializers.Serializer):
    FREE = serializers.IntegerField()
    RENTED = serializers.IntegerField()
    MAINTENANCE = serializers.IntegerField()
    SOLD = serializers.IntegerField()


class PortfolioSerializer(serializers.Serializer):
    properties = serializers.IntegerField()
    buildings = serializers.IntegerField()
    units = serializers.IntegerField()
    units_by_status = UnitsByStatusSerializer()
    units_by_category = UnitCategoryCountSerializer(many=True)
    occupancy_rate = serializers.FloatField(allow_null=True)


class EndingLeaseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    tenant = serializers.CharField()
    unit = serializers.CharField()
    end_date = serializers.DateField()
    days_left = serializers.IntegerField()
    monthly_rent = serializers.DecimalField(help_text="Loyer + charges", **MONEY)


class LeasesSummarySerializer(serializers.Serializer):
    active = serializers.IntegerField()
    drafts = serializers.IntegerField()
    tenants = serializers.IntegerField()
    monthly_rent_roll = serializers.DecimalField(**MONEY)
    ending_soon = EndingLeaseSerializer(many=True)


class MonthlyFinanceSerializer(serializers.Serializer):
    month = serializers.CharField(help_text="AAAA-MM")
    expected = serializers.DecimalField(**MONEY)
    collected = serializers.DecimalField(**MONEY)
    rate = serializers.FloatField(allow_null=True)


class MonthRecoverySerializer(serializers.Serializer):
    expected = serializers.DecimalField(**MONEY)
    collected = serializers.DecimalField(**MONEY)
    rate = serializers.FloatField(allow_null=True)
    payments = serializers.IntegerField(help_text="Paiements enregistrés depuis le début du mois")


class AgingBucketSerializer(serializers.Serializer):
    bucket = serializers.ChoiceField(choices=["0-30", "31-60", "61-90", "90+"])
    amount = serializers.DecimalField(**MONEY)
    count = serializers.IntegerField()


class OverdueTenantSerializer(serializers.Serializer):
    lease_id = serializers.IntegerField(allow_null=True)
    tenant = serializers.CharField()
    unit = serializers.CharField()
    count = serializers.IntegerField(help_text="Échéances en retard")
    amount = serializers.DecimalField(**MONEY)
    days_late = serializers.IntegerField(help_text="Retard de la plus ancienne échéance")


class OverdueSerializer(serializers.Serializer):
    amount = serializers.DecimalField(**MONEY)
    count = serializers.IntegerField()
    tenants = serializers.IntegerField()
    aging = AgingBucketSerializer(many=True)
    by_tenant = OverdueTenantSerializer(many=True, help_text="Un locataire par ligne, les plus gros montants d'abord (6 au plus)")


class ScheduleRowSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    due_date = serializers.DateField()
    amount_due = serializers.DecimalField(**MONEY)
    remaining = serializers.DecimalField(**MONEY)
    days_late = serializers.IntegerField()
    tenant = serializers.CharField()
    unit = serializers.CharField()
    lease_id = serializers.IntegerField(allow_null=True)


class MethodTotalSerializer(serializers.Serializer):
    code = serializers.CharField()
    label = serializers.CharField()
    amount = serializers.DecimalField(**MONEY)
    count = serializers.IntegerField()


class RecentPaymentSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    date = serializers.DateTimeField()
    amount = serializers.DecimalField(**MONEY)
    method = serializers.CharField()
    method_code = serializers.CharField()
    payer = serializers.CharField()


class FinanceSummarySerializer(serializers.Serializer):
    monthly = MonthlyFinanceSerializer(many=True)
    period_collected = serializers.DecimalField(**MONEY)
    period_expected = serializers.DecimalField(**MONEY)
    this_month = MonthRecoverySerializer()
    overdue = OverdueSerializer()
    late = ScheduleRowSerializer(many=True)
    upcoming = ScheduleRowSerializer(many=True)
    upcoming_total = serializers.DecimalField(help_text="Reste dû sur les 30 prochains jours", **MONEY)
    upcoming_count = serializers.IntegerField()
    by_method = MethodTotalSerializer(many=True)
    recent_payments = RecentPaymentSerializer(many=True)


class TicketsByStatusSerializer(serializers.Serializer):
    OPEN = serializers.IntegerField()
    IN_PROGRESS = serializers.IntegerField()
    WAITING = serializers.IntegerField()
    RESOLVED = serializers.IntegerField()
    CLOSED = serializers.IntegerField()


class MonthlyTicketsSerializer(serializers.Serializer):
    month = serializers.CharField(help_text="AAAA-MM")
    created = serializers.IntegerField()
    resolved = serializers.IntegerField()


class TicketCategoryCountSerializer(serializers.Serializer):
    label = serializers.CharField()
    count = serializers.IntegerField()


class OpenTicketSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    unit = serializers.CharField()
    category = serializers.CharField()
    priority = serializers.ChoiceField(choices=MaintenanceTicket.PRIORITY_CHOICES)
    status = serializers.ChoiceField(choices=MaintenanceTicket.STATUS_CHOICES)
    description = serializers.CharField()
    age_days = serializers.IntegerField()


class MaintenanceSummarySerializer(serializers.Serializer):
    open = serializers.IntegerField()
    urgent_open = serializers.IntegerField()
    by_status = TicketsByStatusSerializer()
    monthly = MonthlyTicketsSerializer(many=True)
    avg_resolution_days = serializers.FloatField(allow_null=True)
    by_category = TicketCategoryCountSerializer(many=True)
    recent_open = OpenTicketSerializer(many=True)


class MonthlyInterestCountSerializer(serializers.Serializer):
    month = serializers.CharField(help_text="AAAA-MM")
    count = serializers.IntegerField()


class TopListingSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    listing_type = serializers.ChoiceField(choices=Listing.LISTING_TYPE)
    price = serializers.DecimalField(**MONEY)
    interests = serializers.IntegerField()
    cover = serializers.URLField(allow_null=True)


class RecentInterestSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    prospect = serializers.CharField()
    source = serializers.CharField()
    listing_id = serializers.IntegerField()
    listing = serializers.CharField()
    created_at = serializers.DateTimeField()


class UnitRefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    reference = serializers.CharField()


class ListingsSummarySerializer(serializers.Serializer):
    published = serializers.IntegerField()
    unlisted_count = serializers.IntegerField(help_text="Lots libres sans annonce publiée ni brouillon")
    unlisted_units = UnitRefSerializer(many=True, help_text="Les 12 premiers, par référence")
    drafts = serializers.IntegerField()
    interests_period = serializers.IntegerField()
    interests_30d = serializers.IntegerField()
    monthly_interests = MonthlyInterestCountSerializer(many=True)
    top_listings = TopListingSerializer(many=True)
    recent_interests = RecentInterestSerializer(many=True)


class InsightItemSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=INSIGHT_KINDS)
    severity = serializers.ChoiceField(choices=["danger", "warning", "info", "success"])
    title = serializers.CharField()
    meta = serializers.CharField(help_text="Contexte court : noms, lot, période")
    amount = serializers.DecimalField(allow_null=True, **MONEY)
    count = serializers.IntegerField(allow_null=True)
    date = serializers.DateField(allow_null=True)
    href = serializers.CharField()


class DashboardSerializer(serializers.Serializer):
    generated_at = serializers.DateTimeField()
    months = serializers.IntegerField()
    portfolio = PortfolioSerializer(allow_null=True)
    leases = LeasesSummarySerializer(allow_null=True)
    finance = FinanceSummarySerializer(allow_null=True)
    maintenance = MaintenanceSummarySerializer(allow_null=True)
    listings = ListingsSummarySerializer(allow_null=True)
    insights = InsightItemSerializer(many=True)


class NavCountersSerializer(serializers.Serializer):
    properties = serializers.IntegerField(allow_null=True)
    overdue_schedules = serializers.IntegerField(allow_null=True)
    open_tickets = serializers.IntegerField(allow_null=True)
