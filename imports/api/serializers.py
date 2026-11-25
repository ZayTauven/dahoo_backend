from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from imports.columns import BY_KEY
from imports.commit import FIRST_PERIODS
from imports.plan import ROW_STATUSES

MONEY = {"max_digits": 16, "decimal_places": 2}


class ImportFileSerializer(serializers.Serializer):
    file = serializers.FileField(help_text="Fichier Excel (.xlsx) ou CSV")


class ImportCommitSerializer(ImportFileSerializer):
    first_period = serializers.ChoiceField(choices=FIRST_PERIODS, default="CURRENT", help_text="Premier loyer créé")
    skip_errors = serializers.BooleanField(default=False, help_text="Importer les lignes valides, ignorer les autres")


class ImportMessageSerializer(serializers.Serializer):
    column = serializers.CharField()
    text = serializers.CharField()
    error = serializers.BooleanField()


class ImportRowSerializer(serializers.Serializer):
    line = serializers.IntegerField()
    status = serializers.ChoiceField(choices=ROW_STATUSES)
    property_name = serializers.CharField(allow_blank=True)
    unit = serializers.CharField(allow_blank=True)
    owner_name = serializers.SerializerMethodField()
    tenant_name = serializers.SerializerMethodField()
    rent = serializers.DecimalField(**MONEY)
    arrears = serializers.DecimalField(**MONEY)
    start = serializers.DateField(allow_null=True)
    messages = serializers.SerializerMethodField()

    def get_owner_name(self, row) -> str:
        return f"{row.owner[0]} {row.owner[1]}".strip() if row.owner else ""

    def get_tenant_name(self, row) -> str:
        return f"{row.tenant[0]} {row.tenant[1]}".strip() if row.tenant else ""

    @extend_schema_field(ImportMessageSerializer(many=True))
    def get_messages(self, row):
        return [{"column": BY_KEY[m.column].header, "text": m.text, "error": m.error} for m in row.messages]


class ImportSummarySerializer(serializers.Serializer):
    rows = serializers.IntegerField()
    ready = serializers.IntegerField()
    warnings = serializers.IntegerField()
    skipped = serializers.IntegerField()
    errors = serializers.IntegerField()
    properties = serializers.IntegerField()
    units = serializers.IntegerField()
    owners = serializers.IntegerField()
    tenants = serializers.IntegerField()
    leases = serializers.IntegerField()
    monthly_rent = serializers.DecimalField(**MONEY)
    arrears = serializers.DecimalField(**MONEY)


class ImportPreviewSerializer(serializers.Serializer):
    summary = ImportSummarySerializer()
    problems = serializers.ListField(child=serializers.CharField(), help_text="Ce qui bloque tout l'import (quota)")
    ignored_columns = serializers.ListField(child=serializers.CharField())
    rows = ImportRowSerializer(many=True)
