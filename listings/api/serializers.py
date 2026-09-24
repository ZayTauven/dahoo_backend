from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from listings.models import Listing, ListingPhoto, Prospect, ProspectInterest
from listings.photos import ALLOWED_FORMATS, MAX_PHOTO_SIZE, cover_url
from organizations.scoping import OrganizationScopedRelatedField
from properties.models import Unit


class ListingSerializer(serializers.ModelSerializer):
    unit = OrganizationScopedRelatedField(
        queryset=Unit.objects.all(), organization_lookup="building__property__organization"
    )
    unit_label = serializers.CharField(source="unit.label", read_only=True)
    cover = serializers.SerializerMethodField()
    photos_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Listing
        fields = [
            "id",
            "unit",
            "unit_label",
            "created_by",
            "title",
            "description",
            "listing_type",
            "price",
            "status",
            "cover",
            "photos_count",
            "published_at",
            "created_at",
        ]
        # Le statut change uniquement via publier / dépublier.
        read_only_fields = ["created_by", "status", "published_at", "created_at"]
        extra_kwargs = {"price": {"min_value": 0}}

    @extend_schema_field(OpenApiTypes.URI)
    def get_cover(self, listing):
        return cover_url(self.context.get("request"), listing)


class ListingPhotoSerializer(serializers.ModelSerializer):
    """Photo d'annonce : envoi multipart du fichier `image`, lecture via `url` (absolue)."""

    image = serializers.ImageField(write_only=True)
    url = serializers.ImageField(source="image", read_only=True)

    class Meta:
        model = ListingPhoto
        fields = ["id", "listing", "image", "url", "alt", "position", "created_at"]
        read_only_fields = ["listing", "created_at"]
        extra_kwargs = {"position": {"required": False}}

    def validate_image(self, image):
        if image.size > MAX_PHOTO_SIZE:
            raise serializers.ValidationError("Image trop volumineuse (8 Mo maximum).")
        # ImageField a déjà vérifié avec Pillow que le fichier est une image lisible.
        if getattr(getattr(image, "image", None), "format", None) not in ALLOWED_FORMATS:
            raise serializers.ValidationError("Format non accepté : JPEG, PNG ou WebP uniquement.")
        return image


class ListingPhotoUpdateSerializer(ListingPhotoSerializer):
    """Modification d'une photo : texte alternatif et ordre d'affichage (le fichier ne change pas)."""

    image = None

    class Meta(ListingPhotoSerializer.Meta):
        fields = ["id", "listing", "url", "alt", "position", "created_at"]


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


class PublicInterestReceiptSerializer(serializers.Serializer):
    """Accusé de réception d'une demande publique (sans les données du prospect)."""

    id = serializers.IntegerField()
    listing = serializers.IntegerField(source="listing_id")
    created_at = serializers.DateTimeField()


class PublicInterestSerializer(ProspectInterestSerializer):
    """Réponse publique : on ne renvoie pas les données du prospect."""

    def to_representation(self, instance):
        return PublicInterestReceiptSerializer(instance).data
