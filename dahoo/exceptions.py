from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import ProtectedError
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound, ValidationError
from rest_framework.views import exception_handler


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Suppression impossible : cet élément est encore utilisé."
    default_code = "conflict"


PROTECTED_MESSAGES = {
    "LeaseContract": "des baux y sont rattachés. Terminez ou annulez-les d'abord.",
    "SaleContract": "des ventes y sont rattachées.",
    "Payment": "des paiements y sont rattachés.",
    "MaintenanceTicket": "des tickets de maintenance y sont rattachés.",
}


def protected_message(exc):
    """« Suppression impossible : des baux y sont rattachés… » selon le premier objet qui bloque."""
    blocking = next(iter(exc.protected_objects), None)
    reason = PROTECTED_MESSAGES.get(type(blocking).__name__, "d'autres données y sont rattachées.")
    return f"Suppression impossible : {reason}"


def api_exception_handler(exc, context):
    """
    - ValidationError Django (modèles, services) → 400 au lieu de 500 ;
    - suppression bloquée par une clé protégée (ex. un lot qui a des baux) → 409 avec un message clair ;
    - 404 de get_object_or_404 → message français (le message Django par défaut est en anglais).
    """
    if isinstance(exc, DjangoValidationError):
        detail = exc.message_dict if hasattr(exc, "error_dict") else {"detail": exc.messages}
        exc = ValidationError(detail)
    elif isinstance(exc, ProtectedError):
        exc = Conflict(protected_message(exc))
    elif isinstance(exc, Http404):
        exc = NotFound("Élément introuvable.")
    return exception_handler(exc, context)
