from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from access.catalog import CAPABILITIES
from access.services import get_role_capabilities
from organizations.context import resolve_organization

from .serializers import LoginSerializer, MeCapabilitiesSerializer, MeSerializer


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
