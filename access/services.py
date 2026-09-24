from django.db import transaction

from access.catalog import CAPABILITIES, SYSTEM_ROLES, describe
from access.models import Capability, Role, RoleCapability


def get_role_capabilities(role):
    if role is None:
        return set()
    return set(role.capabilities.values_list("code", flat=True))


def set_role_capabilities(role, codes):
    """Remplace les capabilities d'un rôle par `codes` (codes du catalogue)."""
    wanted = set(Capability.objects.filter(code__in=codes).values_list("id", flat=True))
    current = set(RoleCapability.objects.filter(role=role).values_list("capability_id", flat=True))
    RoleCapability.objects.filter(role=role, capability_id__in=current - wanted).delete()
    RoleCapability.objects.bulk_create(
        [RoleCapability(role=role, capability_id=cap_id) for cap_id in wanted - current]
    )


@transaction.atomic
def sync_capabilities():
    """
    Aligne la base sur access/catalog.py. Idempotent.
    - crée ou met à jour les capabilities du catalogue (avec leur libellé) ;
    - supprime celles qui n'y figurent plus (retirées aussi des rôles personnalisés) ;
    - aligne les rôles système.
    """
    for code in CAPABILITIES:
        capability, _ = Capability.objects.get_or_create(code=code)
        if capability.description != describe(code):
            capability.description = describe(code)
            capability.save(update_fields=["description"])
    Capability.objects.exclude(code__in=CAPABILITIES).delete()

    for role_code, spec in SYSTEM_ROLES.items():
        role, created = Role.objects.get_or_create(code=role_code, defaults={"label": spec["label"]})
        if not created and role.label != spec["label"]:
            role.label = spec["label"]
            role.save(update_fields=["label"])
        set_role_capabilities(role, spec["capabilities"])

