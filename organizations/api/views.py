from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from mailing.accounts import send_password_temporary
from organizations.models import Membership
from organizations.scoping import OrganizationScopedMixin
from subscriptions.services import check_quota
from users.api.serializers import TemporaryPasswordSerializer
from users.passwords import ensure_agency_can_reset, reset_password

from .serializers import MembershipCreateSerializer, MembershipSerializer, OrganizationSerializer


class CurrentOrganizationAPIView(OrganizationScopedMixin, generics.RetrieveUpdateAPIView):
    capability_resource = "organization"
    serializer_class = OrganizationSerializer

    def get_object(self):
        return self.organization


class MemberListCreateAPIView(OrganizationScopedMixin, generics.ListCreateAPIView):
    capability_resource = "member"
    queryset = Membership.objects.select_related("user", "role").order_by("id")

    def get_serializer_class(self):
        if self.request.method == "POST":
            return MembershipCreateSerializer
        return MembershipSerializer

    @extend_schema(request=MembershipCreateSerializer, responses={201: MembershipSerializer})
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        check_quota(self.organization, "member")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = serializer.save()
        return Response(MembershipSerializer(membership).data, status=status.HTTP_201_CREATED)


class MemberResetPasswordAPIView(OrganizationScopedMixin, APIView):
    """Mot de passe oublié d'un membre : génère un mot de passe provisoire à lui transmettre."""

    required_capability = "member.update"

    @extend_schema(request=None, responses=TemporaryPasswordSerializer)
    def post(self, request, pk):
        membership = get_object_or_404(Membership.objects.select_related("user"), pk=pk, organization=self.organization)
        if membership.user_id == request.user.id:
            raise ValidationError({"detail": "Changez votre propre mot de passe depuis votre compte."})
        ensure_agency_can_reset(self.organization, membership.user)
        password = reset_password(membership.user)
        send_password_temporary(membership.user, f"{request.user.first_name} {request.user.last_name}".strip())
        return Response({"temporary_password": password})


class MemberDetailAPIView(OrganizationScopedMixin, generics.RetrieveUpdateAPIView):
    capability_resource = "member"
    queryset = Membership.objects.select_related("user", "role")
    serializer_class = MembershipSerializer

    def perform_update(self, serializer):
        if serializer.instance.user_id == self.request.user.id:
            raise ValidationError({"detail": "Vous ne pouvez pas modifier votre propre rôle ou accès."})
        # Une réactivation compte comme une création : sinon la limite d'utilisateurs se contourne.
        if serializer.validated_data.get("is_active") and not serializer.instance.is_active:
            check_quota(self.organization, "member")
        serializer.save()
