from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from leases.models import LeaseContract, Tenant
from leases.services import activate_lease, change_lease_status
from leases.tenants import tenant_name_subquery
from organizations.scoping import OrganizationScopedMixin

from payments.schedules import disable_auto_schedules, enable_auto_schedules, preview_auto_schedules

from .serializers import (
    AutoSchedulesPreviewSerializer,
    AutoSchedulesSerializer,
    LeaseContractSerializer,
    LeaseWithSchedulesSerializer,
    TenantSerializer,
)


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
    search_fields = ["tenant__first_name", "tenant__last_name", "tenant__phone", "unit__reference"]
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


class LeaseActivateAPIView(OrganizationScopedMixin, APIView):
    required_capability = "lease.activate"

    @extend_schema(request=AutoSchedulesSerializer, responses=LeaseWithSchedulesSerializer)
    def post(self, request, pk):
        contract = get_object_or_404(LeaseContract, pk=pk, organization=self.organization)
        options = AutoSchedulesSerializer(data=request.data, context={"lease": contract})
        options.is_valid(raise_exception=True)
        contract, created = activate_lease(contract, **options.validated_data)
        contract.created_schedules = len(created)
        return Response(LeaseWithSchedulesSerializer(contract, context={"request": request}).data)


class LeaseAutoSchedulesAPIView(OrganizationScopedMixin, APIView):
    """
    Échéancier automatique d'un bail. GET : aperçu de ce qui serait créé (aussi pour un brouillon,
    avant l'activation) ; POST : l'active sur un bail actif ; DELETE : arrête les créations.
    """

    capability_resource = "payment.schedule"

    def get_lease(self, pk):
        return get_object_or_404(LeaseContract, pk=pk, organization=self.organization)

    @extend_schema(responses=AutoSchedulesPreviewSerializer)
    def get(self, request, pk):
        return Response(AutoSchedulesPreviewSerializer(preview_auto_schedules(self.get_lease(pk))).data)

    @extend_schema(request=AutoSchedulesSerializer, responses=LeaseWithSchedulesSerializer)
    def post(self, request, pk):
        contract = self.get_lease(pk)
        if contract.status != "ACTIVE":
            raise ValidationError({"status": "L'échéancier automatique ne s'applique qu'à un bail actif."})
        options = AutoSchedulesSerializer(data=request.data, context={"lease": contract})
        options.is_valid(raise_exception=True)
        contract, created = enable_auto_schedules(
            contract, schedules_from=options.validated_data.get("schedules_from") or contract.start_date
        )
        contract.created_schedules = len(created)
        return Response(LeaseWithSchedulesSerializer(contract, context={"request": request}).data)

    @extend_schema(request=None, responses=LeaseContractSerializer)
    def delete(self, request, pk):
        contract = disable_auto_schedules(self.get_lease(pk))
        return Response(LeaseContractSerializer(contract, context={"request": request}).data)


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
