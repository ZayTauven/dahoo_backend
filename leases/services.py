from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

# Transitions autorisées : statut actuel -> statuts possibles
LEASE_TRANSITIONS = {
    "DRAFT": ["ACTIVE", "CANCELLED"],
    "ACTIVE": ["TERMINATED", "COMPLETED", "CANCELLED"],
    "TERMINATED": ["COMPLETED"],
}

# Statut du lot selon le statut du bail
UNIT_STATUS_ON_LEASE = {
    "ACTIVE": "RENTED",
    "TERMINATED": "FREE",
    "COMPLETED": "FREE",
    "CANCELLED": "FREE",
}


@transaction.atomic
def change_lease_status(contract, new_status):
    from leases.models import LeaseContract

    contract = LeaseContract.objects.select_for_update().select_related("unit").get(pk=contract.pk)
    previous = contract.status
    if new_status not in LEASE_TRANSITIONS.get(previous, []):
        raise ValidationError(
            {"status": f"Transition non autorisée : {contract.get_status_display()} → {new_status}."}
        )

    if new_status == "ACTIVE":
        other_active = LeaseContract.objects.filter(unit=contract.unit, status="ACTIVE").exclude(pk=contract.pk)
        if other_active.exists():
            raise ValidationError({"unit": "Ce lot a déjà un bail actif."})
        if contract.signed_at is None:
            contract.signed_at = timezone.now()

    contract.status = new_status
    contract.save(update_fields=["status", "signed_at"])

    # Un brouillon annulé n'a jamais occupé le lot : on ne touche pas à son statut.
    if previous != "DRAFT" or new_status == "ACTIVE":
        contract.unit.status = UNIT_STATUS_ON_LEASE[new_status]
        contract.unit.save(update_fields=["status"])
    return contract
