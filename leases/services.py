from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

# Transitions autorisées : statut actuel -> statuts possibles
LEASE_TRANSITIONS = {
    "DRAFT": ["ACTIVE", "CANCELLED"],
    "ACTIVE": ["TERMINATED", "COMPLETED", "CANCELLED"],
    "TERMINATED": ["COMPLETED"],
}

# Un lot vendu ou en travaux ne peut pas être loué.
UNIT_STATUS_BLOCKING = ("MAINTENANCE", "SOLD")

# Statut du lot selon le statut du bail
UNIT_STATUS_ON_LEASE = {
    "ACTIVE": "RENTED",
    "TERMINATED": "FREE",
    "COMPLETED": "FREE",
    "CANCELLED": "FREE",
}


@transaction.atomic
def change_lease_status(contract, new_status, *, ended_on=None):
    from leases.models import LeaseContract

    contract = LeaseContract.objects.select_for_update().select_related("unit").get(pk=contract.pk)
    previous = contract.status
    if new_status not in LEASE_TRANSITIONS.get(previous, []):
        target = dict(LeaseContract.STATUS_CHOICES).get(new_status, new_status)
        raise ValidationError(
            {"status": f"Transition non autorisée : {contract.get_status_display()} → {target}."}
        )

    if new_status == "ACTIVE":
        other_active = LeaseContract.objects.filter(unit=contract.unit, status="ACTIVE").exclude(pk=contract.pk)
        if other_active.exists():
            raise ValidationError({"unit": "Ce lot a déjà un bail actif."})
        if contract.unit.status in UNIT_STATUS_BLOCKING:
            raise ValidationError(
                {"unit": f"Ce lot est « {contract.unit.get_status_display()} » : remettez-le en « Libre » avant d'activer le bail."}
            )
        if contract.signed_at is None:
            contract.signed_at = timezone.now()

    contract.status = new_status
    if previous == "ACTIVE" and new_status in ("TERMINATED", "COMPLETED"):
        contract.ended_on = ended_on or timezone.localdate()
    contract.save(update_fields=["status", "signed_at", "ended_on"])

    # Le lot n'est modifié que si le bail l'occupait ou va l'occuper : un brouillon annulé ne l'a
    # jamais occupé, et un bail résilié l'a déjà libéré (le lot a pu être reloué entre-temps).
    if new_status == "ACTIVE" or previous == "ACTIVE":
        contract.unit.status = UNIT_STATUS_ON_LEASE[new_status]
        contract.unit.save(update_fields=["status"])
    if new_status == "ACTIVE":
        # Le lot est pris : ses annonces de location ne sont plus d'actualité.
        contract.unit.listings.filter(listing_type="RENT", status__in=("PUBLISHED", "SUSPENDED")).update(status="CLOSED")

    # Plus de loyer après le départ, qu'il soit anticipé ou au terme.
    if new_status in ("TERMINATED", "CANCELLED") or (new_status == "COMPLETED" and previous == "ACTIVE"):
        from payments.schedules import drop_future_schedules

        drop_future_schedules(contract, today=contract.ended_on)
    return contract


@transaction.atomic
def activate_lease(contract, *, auto_schedules=True, schedules_from=None, with_deposit=False):
    """
    Active le bail puis, si demandé, crée l'échéance de la caution et lance l'échéancier automatique.
    Renvoie (bail, échéances créées).
    """
    from payments.schedules import create_deposit, enable_auto_schedules

    contract = change_lease_status(contract, "ACTIVE")
    deposit = create_deposit(contract) if with_deposit else None
    created = [deposit] if deposit else []
    if not auto_schedules:
        return contract, created
    contract, rents = enable_auto_schedules(contract, schedules_from=schedules_from or contract.start_date)
    return contract, created + rents
