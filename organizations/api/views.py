from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from organizations.models import Membership
from organizations.scoping import OrganizationScopedMixin
from subscriptions.services import check_quota

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


class MemberDetailAPIView(OrganizationScopedMixin, generics.RetrieveUpdateAPIView):
    capability_resource = "member"
    queryset = Membership.objects.select_related("user", "role")
    serializer_class = MembershipSerializer

    def perform_update(self, serializer):
        if serializer.instance.user_id == self.request.user.id:
            raise ValidationError({"detail": "Vous ne pouvez pas modifier votre propre rôle ou accès."})
        serializer.save()
