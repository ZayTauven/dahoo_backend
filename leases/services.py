from django.core.exceptions import ValidationError


LEASE_TRANSITIONS = {
    "DRAFT": ["ACTIVE"],
    "ACTIVE": ["TERMINATED", "COMPLETED", "CANCELLED"],
    "TERMINATED": ["COMPLETED"],
}


def change_lease_status(contract, new_status):
    allowed = LEASE_TRANSITIONS.get(contract.status, [])
    if new_status not in allowed:
        raise ValidationError("Transition non autorisée")

    contract.status = new_status
    contract.save()


def activate_lease(contract):
    if contract.status != "DRAFT":
        raise ValidationError("Seul un contrat brouillon peut être activé")
    contract.status = "ACTIVE"
    contract.save()


def terminate_lease(contract):
    if contract.status != "ACTIVE":
        raise ValidationError("Seul un contrat actif peut être résilié")
    contract.status = "TERMINATED"
    contract.save()


def complete_lease(contract):
    if contract.status not in ["ACTIVE", "TERMINATED"]:
        raise ValidationError("Seuls les contrats actifs ou résiliés peuvent être complétés")
    contract.status = "COMPLETED"
    contract.save()


def cancel_lease(contract):
    if contract.status != "ACTIVE":
        raise ValidationError("Seul un contrat actif peut être annulé")
    contract.status = "CANCELLED"
    contract.save()
