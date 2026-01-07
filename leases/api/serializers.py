from rest_framework import serializers
from leases.models import LeaseContract


class LeaseContractCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaseContract
        fields = [
            "unit",
            "tenant",
            "start_date",
            "end_date",
            "rent_amount",
            "charges_amount",
            "deposit_amount",
            "payment_frequency",
        ]


class LeaseContractSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaseContract
        fields = "__all__"
