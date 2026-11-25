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
    # Reprise d'un parc depuis un tableur (biens, lots, bailleurs, locataires, baux)
    "portfolio.import",
    # Contrats et locataires
    *_crud("tenant"),
    *_crud("lease", ("view", "create", "update")),
    "lease.activate",
    "lease.terminate",
    "lease.complete",
    "lease.cancel",
    # Entrée et sortie : états des lieux, caution
    *_crud("inspection"),
    "deposit.view",
    "deposit.settle",
    "deposit.cancel",
    # Paiements
    *_crud("payment", ("view", "create")),
    "payment.allocate",
    "payment.cancel",
    *_crud("payment.schedule"),
    *_crud("payment.reminder", ("view", "create")),
    # Bailleurs : fiches, dépenses déduites et reversements
    *_crud("owner"),
    *_crud("expense"),
    *_crud("owner.payout", ("view", "create")),
    "owner.payout.cancel",
    # Maintenance
    *_crud("maintenance.ticket"),
    "maintenance.ticket.change_status",
    "maintenance.ticket.assign",
    *_crud("maintenance.log", ("view", "create")),
    # Annonces et prospects
    *_crud("listing"),
    "listing.publish",
    "listing.unpublish",
    "listing.close",
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
        "capabilities": _VIEW
        | {code for code in CAPABILITIES if code.startswith(("payment.", "expense.", "owner.payout.", "deposit."))},
    },
    "VIEWER": {
        "label": "Lecture seule",
        "capabilities": _VIEW,
    },
}


# Libellés affichés dans l'écran de gestion des rôles (stockés dans Capability.description).
RESOURCE_LABELS = {
    "organization": "l'organisation",
    "member": "les membres de l'équipe",
    "property": "les biens",
    "building": "les bâtiments",
    "unit": "les lots",
    "tenant": "les locataires",
    "lease": "les baux",
    "inspection": "les états des lieux",
    "deposit": "les cautions",
    "payment": "les paiements",
    "payment.schedule": "les échéances",
    "payment.reminder": "les relances",
    "owner": "les bailleurs",
    "owner.payout": "les reversements aux bailleurs",
    "expense": "les dépenses",
    "maintenance.ticket": "les tickets de maintenance",
    "maintenance.log": "le journal des interventions",
    "listing": "les annonces",
    "listing.interest": "les demandes des prospects",
    "field_ops.guardian": "les gardiens",
    "field_ops.event": "les événements terrain",
    "analytics.kpi": "les indicateurs des bâtiments",
    "analytics.financial": "les synthèses financières",
    "analytics.insight": "les alertes intelligentes",
    "notification.template": "les modèles de notification",
    "notification.rule": "les règles d'automatisation",
    "subscription": "l'abonnement",
}

ACTION_LABELS = {"view": "Consulter", "create": "Créer", "update": "Modifier", "delete": "Supprimer"}

SPECIAL_LABELS = {
    "unit.change_status": "Changer le statut d'un lot",
    "portfolio.import": "Importer un parc depuis un tableur",
    "lease.activate": "Activer un bail",
    "lease.terminate": "Résilier un bail",
    "lease.complete": "Clôturer un bail",
    "lease.cancel": "Annuler un bail",
    "deposit.settle": "Rendre une caution",
    "deposit.cancel": "Annuler un décompte de caution",
    "payment.allocate": "Affecter un paiement aux échéances",
    "payment.cancel": "Annuler un paiement",
    "owner.payout.cancel": "Annuler un reversement",
    "maintenance.ticket.change_status": "Changer le statut d'un ticket",
    "maintenance.ticket.assign": "Assigner un ticket",
    "listing.publish": "Publier une annonce",
    "listing.unpublish": "Dépublier une annonce",
    "listing.close": "Clôturer une annonce",
}


def describe(code):
    if code in SPECIAL_LABELS:
        return SPECIAL_LABELS[code]
    resource, action = code.rsplit(".", 1)
    return f"{ACTION_LABELS[action]} {RESOURCE_LABELS[resource]}"
