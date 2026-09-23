from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from organizations.models import Membership, Organization

ORGANIZATION_HEADER = "X-Organization-ID"


def resolve_organization(request):
    """
    Détermine l'organisation active de la requête et la mémorise sur `request`
    (`request.organization`, `request.membership`).

    - En-tête X-Organization-ID fourni : l'utilisateur doit en être membre actif
      (un superuser peut cibler n'importe quelle organisation).
    - Sinon : l'utilisateur doit appartenir à une seule organisation active.
    """
    if getattr(request, "_organization_resolved", False):
        return request.organization

    memberships = Membership.objects.filter(
        user=request.user, is_active=True, organization__is_active=True
    ).select_related("organization", "role")

    raw_id = request.headers.get(ORGANIZATION_HEADER)
    membership = None
    if raw_id:
        try:
            org_id = int(raw_id)
        except ValueError:
            raise ValidationError({ORGANIZATION_HEADER: "Identifiant d'organisation invalide."})
        membership = memberships.filter(organization_id=org_id).first()
        if membership:
            organization = membership.organization
        elif request.user.is_superuser:
            organization = Organization.objects.filter(pk=org_id).first()
            if organization is None:
                raise NotFound("Organisation introuvable.")
        else:
            raise PermissionDenied("Vous n'êtes pas membre de cette organisation.")
    else:
        found = list(memberships[:2])
        if not found:
            raise PermissionDenied("Aucune organisation active n'est associée à votre compte.")
        if len(found) > 1:
            raise ValidationError(
                {ORGANIZATION_HEADER: "Vous appartenez à plusieurs organisations : précisez laquelle via cet en-tête."}
            )
        membership = found[0]
        organization = membership.organization

    request.organization = organization
    request.membership = membership
    request._organization_resolved = True
    return organization
