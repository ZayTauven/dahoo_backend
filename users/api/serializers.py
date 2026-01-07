from rest_framework import serializers
from django.contrib.auth import authenticate, get_user_model

User = get_user_model()

from rest_framework import serializers
from django.contrib.auth import authenticate


class LoginSerializer(serializers.Serializer):
    phone = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = authenticate(
            phone=attrs["phone"],
            password=attrs["password"]
        )
        if not user:
            raise serializers.ValidationError("Identifiants invalides")
        attrs["user"] = user
        return attrs




class MeSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "phone", "first_name", "last_name")
