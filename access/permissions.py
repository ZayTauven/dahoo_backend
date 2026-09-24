from rest_framework.permissions import SAFE_METHODS, BasePermission

from access.services import get_role_capabilities
from organizations.context import resolve_organization
from subscriptions.services import ensure_write_access

METHOD_ACTIONS = {
    "GET": "view",
    "HEAD": "view",
    "OPTIONS": "view",
    "POST": "create",
    "PUT": "update",
    "PATCH": "update",
    "DELETE": "delete",
}


def get_required_capability(view, method):
    """
    `required_capability` (action métier : "lease.activate"...) prime sur
    `capability_resource`, qui se décline selon la méthode HTTP :
    GET -> "<ressource>.view", POST -> ".create", PUT/PATCH -> ".update", DELETE -> ".delete".
    """
    explicit = getattr(view, "required_capability", None)
    if explicit:
        return explicit
    resource = getattr(view, "capability_resource", None)
    if resource and method in METHOD_ACTIONS:
        return f"{resource}.{METHOD_ACTIONS[method]}"
    return None


def get_membership_capabilities(request):
    if not hasattr(request, "_capabilities"):
        membership = getattr(request, "membership", None)
        request._capabilities = get_role_capabilities(membership.role if membership else None)
    return request._capabilities


class HasCapability(BasePermission):
    """Exige une organisation active et la capability correspondant à l'action."""

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        organization = resolve_organization(request)
        if request.user.is_superuser:
            return True
        required = get_required_capability(view, request.method)
        if required is not None and required not in get_membership_capabilities(request):
            return False
        if request.method not in SAFE_METHODS:
            ensure_write_access(organization)
        return True


class IsPlatformAdmin(BasePermission):
    """Équipe Dahoo (éditeur du SaaS) : gestion des agences, essais et abonnements."""

    message = "Réservé aux administrateurs de la plateforme Dahoo."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


class IsStaffOrReadOnly(BasePermission):
    """Données de référence communes à toutes les organisations : lecture pour tous, écriture staff."""

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        return request.method in SAFE_METHODS or request.user.is_staff
