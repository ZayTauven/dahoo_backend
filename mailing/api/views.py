from django.core import signing
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from dahoo.throttling import AnonRateThrottle
from mailing.models import EmailOptOut
from mailing.render import OPT_OUT_SALT
from organizations.models import Organization


class OptOutRequestSerializer(serializers.Serializer):
    token = serializers.CharField()


class OptOutResponseSerializer(serializers.Serializer):
    organization = serializers.CharField()


class OptOutAPIView(APIView):
    """Désinscription des rappels d'une agence (lien signé, au bas de chaque rappel). Les quittances continuent."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AnonRateThrottle]

    @extend_schema(request=OptOutRequestSerializer, responses=OptOutResponseSerializer)
    def post(self, request):
        serializer = OptOutRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            data = signing.loads(serializer.validated_data["token"], salt=OPT_OUT_SALT)
            organization = Organization.objects.get(pk=data["o"])
        except (signing.BadSignature, Organization.DoesNotExist):
            raise ValidationError({"detail": "Ce lien n'est pas valide."})
        EmailOptOut.objects.get_or_create(organization=organization, email=data["e"])
        return Response({"organization": organization.name})
