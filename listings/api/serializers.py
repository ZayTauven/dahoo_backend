from rest_framework import serializers
from listings.models import Listing, Prospect, ProspectInterest


class ListingSerializer(serializers.ModelSerializer):
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


class ListingCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Listing
        fields = ["unit", "title", "description", "listing_type", "price"]


class ProspectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Prospect
        fields = ["id", "full_name", "phone", "email", "source", "created_at"]


class ProspectInterestSerializer(serializers.ModelSerializer):
    prospect = ProspectSerializer()

    class Meta:
        model = ProspectInterest
        fields = ["id", "listing", "prospect", "message", "created_at"]
        read_only_fields = ["listing", "created_at"]

    def create(self, validated_data):
        prospect_data = validated_data.pop("prospect")
        phone = prospect_data.get("phone")
        prospect, _ = Prospect.objects.get_or_create(phone=phone, defaults=prospect_data)

        listing = self.context.get("listing")
        interest = ProspectInterest.objects.create(
            listing=listing,
            prospect=prospect,
            **validated_data
        )
        return interest
