from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from inspections.models import Inspection, InspectionItem, InspectionPhoto
from inspections.photos import photo_path
from leases.tenants import tenant_names


class InspectionPhotoSerializer(serializers.ModelSerializer):
    path = serializers.SerializerMethodField(help_text="Chemin d'API signé de l'image")

    class Meta:
        model = InspectionPhoto
        fields = ["id", "item", "path", "created_at"]
        read_only_fields = fields

    @extend_schema_field(OpenApiTypes.STR)
    def get_path(self, photo):
        return photo_path(photo)


class InspectionPhotoUploadSerializer(serializers.Serializer):
    image = serializers.ImageField()
    item = serializers.IntegerField(required=False)


class InspectionItemSerializer(serializers.ModelSerializer):
    entry_condition = serializers.CharField(source="reference.condition", read_only=True, default="")
    entry_note = serializers.CharField(source="reference.note", read_only=True, default="")

    class Meta:
        model = InspectionItem
        fields = ["id", "room", "label", "condition", "note", "position", "entry_condition", "entry_note"]
        read_only_fields = ["position"]


class InspectionSummarySerializer(serializers.ModelSerializer):
    items_count = serializers.IntegerField(read_only=True)
    done_count = serializers.IntegerField(read_only=True)
    photos_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Inspection
        fields = ["id", "lease", "kind", "status", "done_on", "signed_at", "items_count", "done_count", "photos_count"]
        read_only_fields = fields


class InspectionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Inspection
        fields = ["kind", "done_on"]
        extra_kwargs = {"done_on": {"required": False}}


class InspectionSerializer(serializers.ModelSerializer):
    items = InspectionItemSerializer(many=True, read_only=True)
    photos = InspectionPhotoSerializer(many=True, read_only=True)
    tenant_name = serializers.SerializerMethodField()
    unit_label = serializers.CharField(source="lease.unit.label", read_only=True)

    class Meta:
        model = Inspection
        fields = [
            "id", "lease", "kind", "status", "done_on", "electricity_reading", "water_reading", "keys_count", "note",
            "tenant_signer", "tenant_remarks", "signed_at", "tenant_name", "unit_label", "items", "photos",
        ]
        read_only_fields = ["lease", "kind", "status", "tenant_signer", "tenant_remarks", "signed_at"]

    def get_tenant_name(self, inspection) -> str:
        return tenant_names(inspection.organization)(inspection.lease.tenant)


class InspectionSignSerializer(serializers.Serializer):
    tenant_signer = serializers.CharField(max_length=150)
    tenant_remarks = serializers.CharField(required=False, allow_blank=True, default="", max_length=2000)
