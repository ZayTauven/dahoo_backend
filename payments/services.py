from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from rest_framework.exceptions import ValidationError

from payments.models import PaymentAllocation, PaymentSchedule

ZERO = Decimal("0")


def allocated_total(queryset):
    return queryset.aggregate(total=Sum("allocated_amount"))["total"] or ZERO


@transaction.atomic
def allocate_payment(payment, allocations):
    """
    Répartit un paiement sur des échéances.
    `allocations` : liste de {"schedule": PaymentSchedule, "amount": Decimal}.
    Refuse de dépasser le montant du paiement ou le reste dû d'une échéance,
    puis recalcule `is_paid` sur chaque échéance touchée.
    """
    if not allocations:
        return []

    schedule_ids = [a["schedule"].pk for a in allocations]
    if len(schedule_ids) != len(set(schedule_ids)):
        raise ValidationError({"allocations": "Une même échéance apparaît plusieurs fois."})

    # Verrouille les échéances pour éviter une double affectation concurrente.
    schedules = {
        s.pk: s for s in PaymentSchedule.objects.select_for_update().filter(pk__in=schedule_ids)
    }

    requested = sum((a["amount"] for a in allocations), ZERO)
    available = payment.amount_paid - allocated_total(payment.allocations.all())
    if requested > available:
        raise ValidationError(
            {"allocations": f"Montant affecté ({requested}) supérieur au montant disponible du paiement ({available})."}
        )

    created = []
    for allocation in allocations:
        schedule = schedules[allocation["schedule"].pk]
        remaining = schedule.amount_due - allocated_total(schedule.allocations.all())
        if allocation["amount"] > remaining:
            raise ValidationError(
                {"allocations": f"L'échéance {schedule.pk} n'a plus que {remaining} à régler."}
            )
        created.append(
            PaymentAllocation.objects.create(
                payment=payment, schedule=schedule, allocated_amount=allocation["amount"]
            )
        )
        schedule.is_paid = allocated_total(schedule.allocations.all()) >= schedule.amount_due
        schedule.save(update_fields=["is_paid"])
    return created
