from rest_framework import serializers

from listings.models import Listing, Prospect, ProspectInterest
from organizations.scoping import OrganizationScopedRelatedField
from properties.models import Unit


class ListingSerializer(serializers.ModelSerializer):
    unit = OrganizationScopedRelatedField(
        queryset=Unit.objects.all(), organization_lookup="building__property__organization"
    )

    class Meta:
        model = Listing
        fields = [
            "id",
            "unit",
            "created_by",
            "title",
            "description",
            "listing_type",
            "price",
            "status",
            "published_at",
            "created_at",
        ]
        # Le statut change uniquement via publier / dépublier.
        read_only_fields = ["created_by", "status", "published_at", "created_at"]
        extra_kwargs = {"price": {"min_value": 0}}


class ProspectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Prospect
        fields = ["id", "full_name", "phone", "email", "source", "created_at"]
        read_only_fields = ["created_at"]
        # L'unicité (organisation, téléphone) est gérée par get_or_create à la création.
        validators = []


class ProspectInterestSerializer(serializers.ModelSerializer):
    prospect = ProspectSerializer()

    class Meta:
        model = ProspectInterest
        fields = ["id", "listing", "prospect", "message", "created_at"]
        read_only_fields = ["listing", "created_at"]

    def create(self, validated_data):
        listing = self.context["listing"]
        organization = listing.unit.building.property.organization
        prospect_data = validated_data.pop("prospect")
        prospect, _ = Prospect.objects.get_or_create(
            organization=organization,
            phone=prospect_data["phone"],
            defaults=prospect_data,
        )
        return ProspectInterest.objects.create(listing=listing, prospect=prospect, **validated_data)


class PublicInterestSerializer(ProspectInterestSerializer):
    """Réponse publique : on ne renvoie pas les données du prospect."""

    def to_representation(self, instance):
        return {"id": instance.id, "listing": instance.listing_id, "created_at": instance.created_at}
