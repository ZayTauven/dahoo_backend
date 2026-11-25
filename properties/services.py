from rest_framework.exceptions import ValidationError


def check_status_change(unit, status):
    """
    « Loué » suit les baux : il vient de l'activation d'un bail et ne se saisit pas à la main ; un lot
    sous bail actif garde ce statut. Renvoie le statut s'il est permis.
    """
    if unit is not None and status == unit.status:
        return status
    if unit is not None and unit.leasecontract_set.filter(status="ACTIVE").exists():
        raise ValidationError("Ce lot a un bail actif : son statut changera à la fin du bail.")
    if status == "RENTED":
        raise ValidationError("Un lot passe en « Loué » à l'activation de son bail.")
    return status
