from django.contrib.auth import get_user_model
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from leases.models import LeaseContract, Tenant
from leases.tenants import person_name, register_tenant
from organizations.scoping import OrganizationScopedRelatedField
from properties.models import Unit

User = get_user_model()


class LeaseContractSerializer(serializers.ModelSerializer):
    unit = OrganizationScopedRelatedField(
        queryset=Unit.objects.all(), organization_lookup="building__property__organization"
    )
    # Identifiant du locataire tel que renvoyé par /leases/tenants/ (doit être locataire de l'organisation).
    tenant = OrganizationScopedRelatedField(
        queryset=User.objects.all(), organization_lookup="tenant_profiles__organization"
    )
    # Libellés en lecture seule, pour éviter au front une requête par ligne.
    unit_label = serializers.CharField(source="unit.label", read_only=True)
    tenant_name = serializers.SerializerMethodField()

    class Meta:
        model = LeaseContract
        fields = [
            "id",
            "status",
            "unit",
            "unit_label",
            "tenant",
            "tenant_name",
            "start_date",
            "end_date",
            "rent_amount",
            "charges_amount",
            "deposit_amount",
            "payment_frequency",
            "created_by",
            "created_at",
            "signed_at",
        ]
        read_only_fields = ["status", "created_by", "created_at", "signed_at"]
        extra_kwargs = {
            "rent_amount": {"min_value": 0},
            "charges_amount": {"min_value": 0},
            "deposit_amount": {"min_value": 0},
        }

    @extend_schema_field(OpenApiTypes.STR)
    def get_tenant_name(self, contract):
        return person_name(contract, "tenant_profile_name", contract.tenant, contract.organization_id)

    def validate(self, attrs):
        start, end = attrs.get("start_date"), attrs.get("end_date")
        if start and end and end <= start:
            raise serializers.ValidationError({"end_date": "La date de fin doit être postérieure au début."})
        return attrs


class TenantSerializer(serializers.ModelSerializer):
    """
    Locataire de l'organisation. `id` est l'identifiant du compte, celui qu'attendent
    `tenant` (bail) et `payer` (paiement). Le téléphone n'est plus modifiable après création.
    """

    id = serializers.IntegerField(source="user_id", read_only=True)
    phone = serializers.CharField(source="user.phone", max_length=20)
    active_leases = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Tenant
        fields = [
            "id", "phone", "first_name", "last_name", "email",
            "id_document_number", "notes", "active_leases", "created_at",
        ]
        read_only_fields = ["created_at"]

    def validate_phone(self, value):
        value = "".join(value.split())
        if self.instance is not None and value != self.instance.user.phone:
            raise serializers.ValidationError("Le téléphone d'un locataire ne peut pas être modifié.")
        organization = self.context["request"].organization
        if self.instance is None and Tenant.objects.filter(organization=organization, user__phone=value).exists():
            raise serializers.ValidationError("Ce numéro est déjà enregistré comme locataire.")
        return value

    def create(self, validated_data):
        phone = validated_data.pop("user")["phone"]
        return register_tenant(self.context["request"].organization, phone=phone, **validated_data)

    def update(self, instance, validated_data):
        validated_data.pop("user", None)
        return super().update(instance, validated_data)
