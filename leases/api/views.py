from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from leases.models import LeaseContract, Tenant
from leases.services import change_lease_status
from leases.tenants import tenant_name_subquery
from organizations.scoping import OrganizationScopedMixin

from .serializers import LeaseContractSerializer, TenantSerializer


def leases_with_labels():
    """Baux avec libellé du lot et nom du locataire (fiche de l'organisation), sans requête par ligne."""
    return LeaseContract.objects.select_related("unit__building__property", "tenant").annotate(
        tenant_profile_name=tenant_name_subquery("tenant")
    )


class LeaseFilter(filters.FilterSet):
    # Identifiants : lot et compte du locataire (celui renvoyé par /leases/tenants/).
    unit = filters.NumberFilter(field_name="unit_id")
    tenant = filters.NumberFilter(field_name="tenant_id")

    class Meta:
        model = LeaseContract
        fields = ["status", "unit", "tenant"]


class LeaseListCreateAPIView(OrganizationScopedMixin, generics.ListCreateAPIView):
    capability_resource = "lease"
    queryset = leases_with_labels().order_by("-created_at")
    serializer_class = LeaseContractSerializer
    filterset_class = LeaseFilter
    ordering_fields = ["start_date", "end_date", "rent_amount", "created_at"]

    def perform_create(self, serializer):
        serializer.save(organization=self.organization, created_by=self.request.user, status="DRAFT")


class LeaseDetailAPIView(OrganizationScopedMixin, generics.RetrieveAPIView):
    capability_resource = "lease"
    queryset = leases_with_labels()
    serializer_class = LeaseContractSerializer


class LeaseTransitionAPIView(OrganizationScopedMixin, APIView):
    target_status = None

    @extend_schema(request=None, responses=LeaseContractSerializer)
    def post(self, request, pk):
        contract = get_object_or_404(LeaseContract, pk=pk, organization=self.organization)
        contract = change_lease_status(contract, self.target_status)
        return Response(LeaseContractSerializer(contract, context={"request": request}).data)


class LeaseActivateAPIView(LeaseTransitionAPIView):
    required_capability = "lease.activate"
    target_status = "ACTIVE"


class LeaseTerminateAPIView(LeaseTransitionAPIView):
    required_capability = "lease.terminate"
    target_status = "TERMINATED"


class LeaseCompleteAPIView(LeaseTransitionAPIView):
    required_capability = "lease.complete"
    target_status = "COMPLETED"


class LeaseCancelAPIView(LeaseTransitionAPIView):
    required_capability = "lease.cancel"
    target_status = "CANCELLED"


class TenantQuerysetMixin(OrganizationScopedMixin):
    capability_resource = "tenant"
    serializer_class = TenantSerializer
    queryset = Tenant.objects.none()  # Modèle de référence pour le schéma OpenAPI (le vrai queryset dépend de la requête).
    search_fields = ["first_name", "last_name", "user__phone", "email"]
    ordering_fields = ["last_name", "created_at", "active_leases"]
    # Les URLs utilisent l'identifiant du compte, comme les champs `tenant` et `payer`.
    lookup_field = "user_id"
    lookup_url_kwarg = "pk"

    def get_queryset(self):
        organization = self.request.organization
        return (
            Tenant.objects.filter(organization=organization)
            .select_related("user")
            .annotate(
                active_leases=Count(
                    "user__lease_contracts",
                    filter=Q(user__lease_contracts__organization=organization, user__lease_contracts__status="ACTIVE"),
                )
            )
            .order_by("last_name", "first_name")
        )


class TenantListCreateAPIView(TenantQuerysetMixin, generics.ListCreateAPIView):
    pass


class TenantDetailAPIView(TenantQuerysetMixin, generics.RetrieveUpdateDestroyAPIView):
    def perform_destroy(self, instance):
        if LeaseContract.objects.filter(organization=instance.organization, tenant=instance.user).exists():
            raise ValidationError({"detail": "Ce locataire a des baux : il ne peut pas être supprimé."})
        instance.delete()
