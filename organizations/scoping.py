from rest_framework import serializers

from access.permissions import HasCapability


class OrganizationScopedMixin:
    """
    Vue dont les données sont cloisonnées par organisation.

    `organization_lookup` est le chemin ORM de l'objet vers son organisation
    (ex. "building__property__organization"). Les objets d'une autre organisation
    sont invisibles : liste filtrée et 404 sur le détail.
    """

    permission_classes = [HasCapability]
    organization_lookup = "organization"

    @property
    def organization(self):
        return self.request.organization

    def get_queryset(self):
        return super().get_queryset().filter(**{self.organization_lookup: self.organization})


class OrganizationScopedRelatedField(serializers.PrimaryKeyRelatedField):
    """
    Clé étrangère limitée aux objets de l'organisation active : un id appartenant à
    une autre organisation est rejeté comme s'il n'existait pas.
    """

    def __init__(self, *, organization_lookup="organization", **kwargs):
        self.organization_lookup = organization_lookup
        super().__init__(**kwargs)

    def get_queryset(self):
        queryset = super().get_queryset()
        request = self.context.get("request")
        organization = getattr(request, "organization", None)
        if organization is None:
            return queryset.none()
        return queryset.filter(**{self.organization_lookup: organization}).distinct()
