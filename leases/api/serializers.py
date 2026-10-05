from django.contrib.auth import get_user_model
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from leases.models import LeaseContract, Tenant
from leases.tenants import person_name, register_tenant
from organizations.scoping import OrganizationScopedRelatedField
from properties.models import Unit
from users.phone import validate_phone

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
            "due_day",
            "auto_schedules",
            "schedules_from",
            "created_by",
            "created_at",
            "signed_at",
        ]
        read_only_fields = ["status", "auto_schedules", "schedules_from", "created_by", "created_at", "signed_at"]
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


class AutoSchedulesSerializer(serializers.Serializer):
    """Échéancier automatique : à l'activation (désactivable) ou pour un bail déjà actif."""

    auto_schedules = serializers.BooleanField(default=True)
    # Première période facturée : début du bail par défaut, ou début de la période en cours pour
    # reprendre un bail ancien sans recréer ses loyers passés.
    schedules_from = serializers.DateField(required=False, allow_null=True)

    def validate_schedules_from(self, value):
        lease = self.context["lease"]
        if value is None:
            return value
        if value < lease.start_date:
            raise serializers.ValidationError("La date doit suivre le début du bail.")
        if lease.end_date and value > lease.end_date:
            raise serializers.ValidationError("La date doit précéder la fin du bail.")
        return value


class LeaseWithSchedulesSerializer(LeaseContractSerializer):
    created_schedules = serializers.IntegerField(read_only=True)

    class Meta(LeaseContractSerializer.Meta):
        fields = [*LeaseContractSerializer.Meta.fields, "created_schedules"]


class AutoSchedulesOptionSerializer(serializers.Serializer):
    schedules_from = serializers.DateField()
    count = serializers.IntegerField()
    total = serializers.DecimalField(max_digits=14, decimal_places=2)
    first_due = serializers.DateField(allow_null=True)
    prorated = serializers.BooleanField(help_text="Une des échéances est calculée au prorata.")


class AutoSchedulesPreviewSerializer(serializers.Serializer):
    """Ce que créerait l'échéancier automatique, aujourd'hui."""

    from_start = AutoSchedulesOptionSerializer()
    # Absent quand le bail commence dans la période en cours ou plus tard, ou que ses loyers passés
    # sont déjà saisis (le choix ne changerait rien).
    from_current = AutoSchedulesOptionSerializer(allow_null=True)
    horizon_days = serializers.IntegerField()


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
        value = validate_phone(value)
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
