from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404

from leases.models import LeaseContract
from leases.services import (
    activate_lease,
    terminate_lease,
    complete_lease,
    cancel_lease,
)
from leases.api.serializers import (
    LeaseContractCreateSerializer,
    LeaseContractSerializer,
)
from users.api.permissions import HasCapability
from leases.services import change_lease_status

class LeaseActivateAPIView(APIView):
    permission_classes = [IsAuthenticated, HasCapability]
    required_capability = "lease.activate"

    def post(self, request, pk):
        contract = get_object_or_404(LeaseContract, pk=pk)
        change_lease_status(contract, "ACTIVE")
        return Response({"status": "activated"})


class LeaseCreateAPIView(APIView):
    permission_classes = [IsAuthenticated, HasCapability]
    required_capability = "lease.create"

    def post(self, request):
        serializer = LeaseContractCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        contract = serializer.save(
            owner=request.user,
            status="DRAFT"
        )

        return Response(
            LeaseContractSerializer(contract).data,
            status=201
        )


class LeaseListAPIView(APIView):
    permission_classes = [IsAuthenticated, HasCapability]
    required_capability = "lease.view"

    def get(self, request):
        qs = LeaseContract.objects.filter(owner=request.user)
        return Response(
            LeaseContractSerializer(qs, many=True).data
        )


class LeaseActivateAPIView(APIView):
    permission_classes = [IsAuthenticated, HasCapability]
    required_capability = "lease.activate"

    def post(self, request, pk):
        contract = get_object_or_404(
            LeaseContract,
            pk=pk,
            owner=request.user
        )
        activate_lease(contract)
        return Response({"status": "activated"})


class LeaseTerminateAPIView(APIView):
    permission_classes = [IsAuthenticated, HasCapability]
    required_capability = "lease.terminate"

    def post(self, request, pk):
        contract = get_object_or_404(
            LeaseContract,
            pk=pk,
            owner=request.user
        )
        terminate_lease(contract)
        return Response({"status": "terminated"})


class LeaseCompleteAPIView(APIView):
    permission_classes = [IsAuthenticated, HasCapability]
    required_capability = "lease.complete"

    def post(self, request, pk):
        contract = get_object_or_404(
            LeaseContract,
            pk=pk,
            owner=request.user
        )
        complete_lease(contract)
        return Response({"status": "completed"})


class LeaseCancelAPIView(APIView):
    permission_classes = [IsAuthenticated, HasCapability]
    required_capability = "lease.cancel"

    def post(self, request, pk):
        contract = get_object_or_404(
            LeaseContract,
            pk=pk,
            owner=request.user
        )
        cancel_lease(contract)
        return Response({"status": "cancelled"})

