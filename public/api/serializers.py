"""
Sérialiseurs du portail public. Chaque champ est listé explicitement : aucune donnée privée
(locataires, bailleurs, prospects, membres, baux, adresse ou position exacte du bien) ne sort.
"""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from listings.models import Listing, ListingPhoto
from listings.photos import cover_url
from organizations.models import Organization
from properties.models import Unit
from public.models import DemoRequest
from public.visibility import similar_listings
from subscriptions.models import SubscriptionPlan

PROPERTY = "unit.building.property"


class PublicAgencySummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ["id", "name", "city"]


class PublicAgencyContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ["id", "name", "city", "phone", "email"]


class PublicListingSerializer(serializers.ModelSerializer):
    cover = serializers.SerializerMethodField()
    city = serializers.CharField(source=f"{PROPERTY}.city")
    neighborhood = serializers.CharField(source=f"{PROPERTY}.neighborhood")
    category = serializers.ChoiceField(source="unit.category", choices=Unit.CATEGORY_CHOICES)
    category_label = serializers.CharField(source="unit.get_category_display")
    surface = serializers.FloatField(source="unit.surface")
    bedrooms = serializers.IntegerField(source="unit.bedrooms", allow_null=True)
    bathrooms = serializers.IntegerField(source="unit.bathrooms", allow_null=True)
    is_furnished = serializers.BooleanField(source="unit.is_furnished")
    agency = PublicAgencySummarySerializer(source=f"{PROPERTY}.organization")

    class Meta:
        model = Listing
        fields = [
            "id", "title", "listing_type", "price", "published_at", "cover",
            "city", "neighborhood", "category", "category_label",
            "surface", "bedrooms", "bathrooms", "is_furnished", "agency",
        ]
        read_only_fields = fields

    @extend_schema_field(OpenApiTypes.URI)
    def get_cover(self, listing):
        return cover_url(self.context.get("request"), listing)


class PublicPhotoSerializer(serializers.ModelSerializer):
    url = serializers.ImageField(source="image", read_only=True)

    class Meta:
        model = ListingPhoto
        fields = ["url", "alt"]


class PublicListingDetailSerializer(PublicListingSerializer):
    photos = PublicPhotoSerializer(many=True, read_only=True)
    parking_spaces = serializers.IntegerField(source="unit.parking_spaces", allow_null=True)
    # Position arrondie à 3 décimales (~100 m) : on situe le quartier, pas le logement.
    latitude = serializers.DecimalField(
        source=f"{PROPERTY}.latitude", max_digits=6, decimal_places=3, allow_null=True
    )
    longitude = serializers.DecimalField(
        source=f"{PROPERTY}.longitude", max_digits=6, decimal_places=3, allow_null=True
    )
    agency = PublicAgencyContactSerializer(source=f"{PROPERTY}.organization")
    similar = serializers.SerializerMethodField()

    class Meta(PublicListingSerializer.Meta):
        fields = PublicListingSerializer.Meta.fields + [
            "description", "photos", "parking_spaces", "latitude", "longitude", "similar",
        ]
        read_only_fields = fields

    @extend_schema_field(PublicListingSerializer(many=True))
    def get_similar(self, listing):
        return PublicListingSerializer(similar_listings(listing), many=True, context=self.context).data


class PublicAgencySerializer(serializers.ModelSerializer):
    listings_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Organization
        fields = ["id", "name", "city", "listings_count"]


class ListingTypeCountsSerializer(serializers.Serializer):
    RENT = serializers.IntegerField(source="rent_count")
    SALE = serializers.IntegerField(source="sale_count")


class PublicAgencyDetailSerializer(PublicAgencySerializer):
    listings_by_type = ListingTypeCountsSerializer(source="*", read_only=True)

    class Meta(PublicAgencySerializer.Meta):
        fields = PublicAgencySerializer.Meta.fields + ["phone", "email", "address", "listings_by_type"]


class TypeCountSerializer(serializers.Serializer):
    listing_type = serializers.ChoiceField(choices=Listing.LISTING_TYPE)
    label = serializers.CharField()
    count = serializers.IntegerField()


class CategoryCountSerializer(serializers.Serializer):
    category = serializers.ChoiceField(choices=Unit.CATEGORY_CHOICES)
    label = serializers.CharField()
    count = serializers.IntegerField()


class CityCountSerializer(serializers.Serializer):
    city = serializers.CharField()
    listings_count = serializers.IntegerField()


class PublicStatsSerializer(serializers.Serializer):
    listings_count = serializers.IntegerField()
    agencies_count = serializers.IntegerField()
    by_type = TypeCountSerializer(many=True)
    by_category = CategoryCountSerializer(many=True)
    cities = CityCountSerializer(many=True)


class PublicPlanSerializer(serializers.ModelSerializer):
    billing_type_label = serializers.CharField(source="get_billing_type_display", read_only=True)

    class Meta:
        model = SubscriptionPlan
        fields = [
            "id", "name", "billing_type", "billing_type_label", "price", "commission_rate",
            "max_properties", "max_units", "max_users",
        ]


class DemoRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = DemoRequest
        fields = [
            "id", "agency_name", "contact_name", "phone", "email", "city", "units_range", "message", "created_at",
        ]
        read_only_fields = ["created_at"]

    def validate_phone(self, value):
        return "".join(value.split())
