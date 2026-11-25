from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from access.catalog import CAPABILITIES
from access.services import get_role_capabilities
from organizations.context import resolve_organization

from mailing.accounts import confirm_email, send_confirmation, send_password_changed, send_password_reset, user_from_reset
from users.passwords import change_password
from users.phone import normalize_phone

from .serializers import (
    ChangeEmailSerializer,
    ChangePasswordSerializer,
    ConfirmEmailSerializer,
    ForgotPasswordSerializer,
    LoginSerializer,
    MeCapabilitiesSerializer,
    MeSerializer,
    ResetPasswordSerializer,
)

User = get_user_model()


class LoginAPIView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "login"

    @extend_schema(request=LoginSerializer, responses={200: dict})
    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data["user"]
        refresh = RefreshToken.for_user(user)

        return Response({
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        })


class MeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=MeSerializer)
    def get(self, request):
        return Response(MeSerializer(request.user).data)

    @extend_schema(request=MeSerializer, responses=MeSerializer)
    def patch(self, request):
        """Préférences d'e-mail (point du jour, alertes). L'adresse se change par /me/email/."""
        serializer = MeSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class ChangeEmailAPIView(APIView):
    """Nouvelle adresse : elle n'est enregistrée qu'une fois confirmée par le lien reçu."""

    permission_classes = [IsAuthenticated]
    throttle_scope = "login"

    @extend_schema(request=ChangeEmailSerializer, responses={204: None})
    def post(self, request):
        serializer = ChangeEmailSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        send_confirmation(request.user, serializer.validated_data["email"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class ConfirmEmailAPIView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "login"

    @extend_schema(request=ConfirmEmailSerializer, responses={204: None})
    def post(self, request):
        serializer = ConfirmEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        confirm_email(serializer.validated_data["token"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class ForgotPasswordAPIView(APIView):
    """
    Envoie un lien à l'adresse confirmée du compte. La réponse est toujours la même : elle ne dit pas si
    le numéro existe, ni s'il a une adresse.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "password_reset"

    @extend_schema(request=ForgotPasswordSerializer, responses={204: None})
    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = normalize_phone(serializer.validated_data["phone"])
        user = User.objects.filter(phone=phone, is_active=True).first()
        # Un message au plus toutes les deux minutes par compte, quelle que soit la provenance des demandes.
        if user and cache.add(f"password-reset:{user.pk}", True, 120):
            send_password_reset(user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ResetPasswordAPIView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "login"

    @extend_schema(request=ResetPasswordSerializer, responses={204: None})
    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = user_from_reset(data["uid"], data["token"])
        try:
            validate_password(data["new_password"], user)
        except DjangoValidationError as error:
            raise ValidationError({"new_password": error.messages})
        change_password(user, data["new_password"])
        send_password_changed(user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ChangePasswordAPIView(APIView):
    """Change son propre mot de passe ; les autres sessions sont fermées et de nouveaux jetons renvoyés."""

    permission_classes = [IsAuthenticated]
    throttle_scope = "login"

    @extend_schema(request=ChangePasswordSerializer, responses={200: dict})
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        change_password(request.user, serializer.validated_data["new_password"])
        send_password_changed(request.user)
        refresh = RefreshToken.for_user(request.user)
        return Response({"refresh": str(refresh), "access": str(refresh.access_token)})


class MeCapabilitiesAPIView(APIView):
    """Capabilities de l'utilisateur dans l'organisation active (en-tête X-Organization-ID si besoin)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=MeCapabilitiesSerializer)
    def get(self, request):
        organization = resolve_organization(request)
        membership = request.membership
        if request.user.is_superuser:
            caps = set(CAPABILITIES)
        else:
            caps = get_role_capabilities(membership.role if membership else None)
        return Response({
            "organization_id": organization.id,
            "role": membership.role.code if membership else None,
            "capabilities": sorted(caps),
        })
