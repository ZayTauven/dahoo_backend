# Catalogue unique des capabilities de l'API et des rôles système.
# Il est synchronisé en base à chaque `migrate` (voir access/apps.py).
# Une capability = "<ressource>.<action>" ; les actions CRUD standard sont
# view / create / update / delete (voir access/permissions.py).

CRUD = ("view", "create", "update", "delete")


def _crud(resource, actions=CRUD):
    return {f"{resource}.{action}" for action in actions}


CAPABILITIES = {
    # Organisation et équipe
    *_crud("organization", ("view", "update")),
    *_crud("member", ("view", "create", "update")),
    # Patrimoine
    *_crud("property"),
    *_crud("building"),
    *_crud("unit"),
    "unit.change_status",
    # Contrats et locataires
    *_crud("tenant"),
    *_crud("lease", ("view", "create")),
    "lease.activate",
    "lease.terminate",
    "lease.complete",
    "lease.cancel",
    # Paiements
    *_crud("payment", ("view", "create")),
    "payment.allocate",
    *_crud("payment.schedule"),
    # Maintenance
    *_crud("maintenance.ticket"),
    "maintenance.ticket.change_status",
    "maintenance.ticket.assign",
    *_crud("maintenance.log", ("view", "create")),
    # Annonces et prospects
    *_crud("listing"),
    "listing.publish",
    "listing.unpublish",
    "listing.interest.view",
    # Terrain
    *_crud("field_ops.guardian"),
    *_crud("field_ops.event", ("view", "create")),
    # Pilotage
    "analytics.kpi.view",
    "analytics.financial.view",
    "analytics.insight.view",
    # Notifications
    *_crud("notification.template", ("view", "create")),
    *_crud("notification.rule", ("view", "create")),
    # Abonnement
    "subscription.view",
}

_VIEW = {code for code in CAPABILITIES if code.endswith(".view")}
_TEAM_ADMIN = {"organization.update", "member.create", "member.update"}

SYSTEM_ROLES = {
    "ORG_ADMIN": {
        "label": "Administrateur d'organisation",
        "capabilities": set(CAPABILITIES),
    },
    "MANAGER": {
        "label": "Gestionnaire",
        "capabilities": set(CAPABILITIES) - _TEAM_ADMIN,
    },
    "ACCOUNTANT": {
        "label": "Comptable",
        "capabilities": _VIEW | {code for code in CAPABILITIES if code.startswith("payment.")},
    },
    "VIEWER": {
        "label": "Lecture seule",
        "capabilities": _VIEW,
    },
}
