from rest_framework.permissions import BasePermission
from users.services import get_user_capabilities


class HasCapability(BasePermission):
    required_capability = None

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False

        required = getattr(view, "required_capability", None)
        if not required:
            return True

        return required in get_user_capabilities(request.user)
