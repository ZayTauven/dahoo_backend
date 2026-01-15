from rest_framework import serializers
from payments.models import PaymentMethod, PaymentSchedule, Payment, PaymentAllocation


class PaymentMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentMethod
        fields = ["id", "code", "label"]


class PaymentScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentSchedule
        fields = ["id", "lease_contract", "sale_contract", "schedule_type", "due_date", "amount_due", "is_paid", "created_at"]


class PaymentAllocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentAllocation
        fields = ["id", "payment", "schedule", "allocated_amount", "created_at"]


class PaymentSerializer(serializers.ModelSerializer):
    allocations = PaymentAllocationSerializer(many=True, read_only=True)

    class Meta:
        model = Payment
        fields = ["id", "payer", "amount_paid", "payment_method", "payment_date", "reference", "note", "created_at", "allocations"]


class PaymentCreateSerializer(serializers.ModelSerializer):
    allocations = serializers.ListField(child=serializers.DictField(), required=False)

    class Meta:
        model = Payment
        fields = ["amount_paid", "payment_method", "reference", "note", "allocations"]

    def create(self, validated_data):
        allocations = validated_data.pop("allocations", [])
        payer = self.context.get("request").user
        payment = Payment.objects.create(payer=payer, **validated_data)

        for a in allocations:
            schedule_id = a.get("schedule_id")
            amount = a.get("amount")
            schedule = PaymentSchedule.objects.get(pk=schedule_id)
            PaymentAllocation.objects.create(payment=payment, schedule=schedule, allocated_amount=amount)
            # update schedule paid flag if covered
            total_alloc = sum([float(x.allocated_amount) for x in schedule.allocations.all()])
            if total_alloc >= float(schedule.amount_due):
                schedule.is_paid = True
                schedule.save()

        return payment
