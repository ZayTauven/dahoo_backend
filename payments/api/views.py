from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404

from users.api.permissions import HasCapability
from payments.models import (
	PaymentMethod,
	PaymentSchedule,
	Payment,
	PaymentAllocation,
)
from .serializers import (
	PaymentMethodSerializer,
	PaymentScheduleSerializer,
	PaymentSerializer,
	PaymentCreateSerializer,
	PaymentAllocationSerializer,
)


class PaymentMethodListCreateAPIView(generics.ListCreateAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "payment.method.view"
	queryset = PaymentMethod.objects.all()
	serializer_class = PaymentMethodSerializer


class PaymentMethodDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "payment.method.view"
	queryset = PaymentMethod.objects.all()
	serializer_class = PaymentMethodSerializer


class PaymentScheduleListAPIView(generics.ListAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "payment.schedule.view"
	serializer_class = PaymentScheduleSerializer

	def get_queryset(self):
		# return schedules related to contracts owned by the user
		user = self.request.user
		return PaymentSchedule.objects.filter(
			models.Q(lease_contract__owner=user) | models.Q(sale_contract__owner=user)
		)


class PaymentScheduleDetailAPIView(generics.RetrieveAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "payment.schedule.view"
	queryset = PaymentSchedule.objects.all()
	serializer_class = PaymentScheduleSerializer


class PaymentListCreateAPIView(generics.ListCreateAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "payment.view"
	serializer_class = PaymentSerializer

	def get_queryset(self):
		# Payments made by the user
		return Payment.objects.filter(payer=self.request.user)

	def get_serializer_class(self):
		if self.request.method == "POST":
			return PaymentCreateSerializer
		return PaymentSerializer

	def perform_create(self, serializer):
		serializer.save(payer=self.request.user)


class PaymentDetailAPIView(generics.RetrieveAPIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "payment.view"
	queryset = Payment.objects.all()
	serializer_class = PaymentSerializer


class PaymentAllocateAPIView(APIView):
	permission_classes = [IsAuthenticated, HasCapability]
	required_capability = "payment.allocate"

	def post(self, request, pk):
		payment = get_object_or_404(Payment, pk=pk, payer=request.user)
		allocations = request.data.get("allocations", [])
		created = []
		for a in allocations:
			schedule_id = a.get("schedule_id")
			amount = a.get("amount")
			schedule = get_object_or_404(PaymentSchedule, pk=schedule_id)
			alloc = PaymentAllocation.objects.create(
				payment=payment,
				schedule=schedule,
				allocated_amount=amount,
			)
			# mark schedule paid if allocated covers amount_due
			total_alloc = sum([float(x.allocated_amount) for x in schedule.allocations.all()])
			if total_alloc >= float(schedule.amount_due):
				schedule.is_paid = True
				schedule.save()
			created.append(PaymentAllocationSerializer(alloc).data)

		return Response({"allocations": created}, status=status.HTTP_201_CREATED)

