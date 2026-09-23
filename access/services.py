from django.db import transaction

from access.catalog import CAPABILITIES, SYSTEM_ROLES
from access.models import Capability, Role, RoleCapability


def get_role_capabilities(role):
    if role is None:
        return set()
    return set(role.capabilities.values_list("code", flat=True))


@transaction.atomic
def sync_capabilities():
    """Crée les capabilities du catalogue et aligne les rôles système. Idempotent."""
    for code in CAPABILITIES:
        Capability.objects.get_or_create(code=code)

    for role_code, spec in SYSTEM_ROLES.items():
        role, created = Role.objects.get_or_create(code=role_code, defaults={"label": spec["label"]})
        if not created and role.label != spec["label"]:
            role.label = spec["label"]
            role.save(update_fields=["label"])

        wanted = set(Capability.objects.filter(code__in=spec["capabilities"]).values_list("id", flat=True))
        current = set(RoleCapability.objects.filter(role=role).values_list("capability_id", flat=True))
        RoleCapability.objects.filter(role=role, capability_id__in=current - wanted).delete()
        RoleCapability.objects.bulk_create(
            [RoleCapability(role=role, capability_id=cap_id) for cap_id in wanted - current]
        )
