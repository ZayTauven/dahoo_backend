from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from leases.models import LeaseContract
from leases.services import change_lease_status
from organizations.scoping import OrganizationScopedMixin

from .serializers import LeaseContractSerializer


class LeaseListCreateAPIView(OrganizationScopedMixin, generics.ListCreateAPIView):
    capability_resource = "lease"
    queryset = LeaseContract.objects.order_by("-created_at")
    serializer_class = LeaseContractSerializer

    def perform_create(self, serializer):
        serializer.save(organization=self.organization, created_by=self.request.user, status="DRAFT")


class LeaseDetailAPIView(OrganizationScopedMixin, generics.RetrieveAPIView):
    capability_resource = "lease"
    queryset = LeaseContract.objects.all()
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
