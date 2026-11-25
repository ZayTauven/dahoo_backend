"""Préparer, valider et rouvrir un état des lieux."""

import re

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from inspections.models import Inspection, InspectionItem

BASE = ["Murs et plafond", "Sol", "Portes et fenêtres", "Prises et éclairage"]
KITCHEN = [*BASE, "Évier et robinetterie", "Placards"]
BATHROOM = [*BASE, "Sanitaires et robinetterie"]


def default_rooms(unit):
    """Pièces et éléments proposés selon le lot ; l'agent complète ou retire sur place."""
    if unit.category == "LAND":
        return [("Terrain", ["Clôture et portail", "Sol et accès"])]
    if unit.category in ("OFFICE", "SHOP"):
        return [("Local", [*BASE, "Vitrine et fermetures"]), ("Sanitaires", BATHROOM)]
    bedrooms = unit.bedrooms
    if bedrooms is None:
        # « T3 » ou « F3 » : un séjour et deux chambres.
        rooms = re.search(r"\b[TF](\d)\b", unit.unit_type or "", re.I)
        bedrooms = max(0, int(rooms[1]) - 1) if rooms else 1
    if unit.category == "STUDIO":
        bedrooms = 0
    bathrooms = max(1, unit.bathrooms or 1)
    rooms = [("Pièce principale" if unit.category == "STUDIO" else "Entrée et séjour", BASE), ("Cuisine", KITCHEN)]
    rooms += [("Chambre" if bedrooms == 1 else f"Chambre {n}", BASE) for n in range(1, min(bedrooms, 10) + 1)]
    rooms += [("Salle de bain" if bathrooms == 1 else f"Salle de bain {n}", BATHROOM) for n in range(1, min(bathrooms, 6) + 1)]
    if unit.is_furnished:
        rooms.append(("Mobilier", ["Meubles", "Literie", "Électroménager", "Vaisselle"]))
    return rooms


@transaction.atomic
def create_inspection(lease, *, kind, user, done_on=None):
    if kind == "ENTRY" and lease.status not in ("DRAFT", "ACTIVE"):
        raise ValidationError({"detail": "Ce bail est terminé : seul l'état des lieux de sortie peut être fait."})
    if kind == "EXIT" and lease.status not in ("ACTIVE", "TERMINATED", "COMPLETED"):
        raise ValidationError({"detail": "Le bail doit avoir commencé pour faire l'état des lieux de sortie."})
    if lease.inspections.filter(kind=kind).exists():
        raise ValidationError({"detail": "Cet état des lieux existe déjà."})
    inspection = Inspection.objects.create(
        organization_id=lease.organization_id, lease=lease, kind=kind, created_by=user, **({"done_on": done_on} if done_on else {}),
    )
    entry = lease.inspections.filter(kind="ENTRY", status="SIGNED").first() if kind == "EXIT" else None
    if entry:
        # Sortie : les mêmes lignes que l'entrée, une à une, pour comparer sans rien oublier.
        rows = [(item.room, item.label, item) for item in entry.items.all()]
    else:
        rows = [(room, label, None) for room, labels in default_rooms(lease.unit) for label in labels]
    InspectionItem.objects.bulk_create(
        InspectionItem(inspection=inspection, room=room, label=label, position=index, reference=reference)
        for index, (room, label, reference) in enumerate(rows)
    )
    return inspection


def ensure_draft(inspection):
    if inspection.status != "DRAFT":
        raise ValidationError({"detail": "Cet état des lieux est validé : rouvrez-le pour le corriger."})


@transaction.atomic
def sign_inspection(inspection, *, user, tenant_signer, tenant_remarks=""):
    inspection = Inspection.objects.select_for_update().get(pk=inspection.pk)
    ensure_draft(inspection)
    missing = inspection.items.filter(condition="").count()
    if missing:
        raise ValidationError({"detail": f"Il reste {missing} élément{'s' if missing > 1 else ''} à regarder : notez leur état ou retirez-les."})
    if not inspection.items.exists():
        raise ValidationError({"detail": "Ajoutez au moins un élément."})
    inspection.status, inspection.signed_at, inspection.signed_by = "SIGNED", timezone.now(), user
    inspection.tenant_signer, inspection.tenant_remarks = tenant_signer.strip(), tenant_remarks.strip()
    inspection.save(update_fields=["status", "signed_at", "signed_by", "tenant_signer", "tenant_remarks"])
    return inspection


@transaction.atomic
def reopen_inspection(inspection):
    """Corriger une erreur ; impossible dès qu'une caution a été rendue sur cette base."""
    inspection = Inspection.objects.select_for_update().get(pk=inspection.pk)
    if inspection.status != "SIGNED":
        raise ValidationError({"detail": "Cet état des lieux n'est pas validé."})
    if inspection.lease.deposit_settlements.filter(cancelled_at__isnull=True).exists():
        raise ValidationError({"detail": "La caution a été réglée sur cette base : annulez d'abord le décompte."})
    if inspection.kind == "ENTRY" and inspection.lease.inspections.filter(kind="EXIT").exists():
        raise ValidationError({"detail": "L'état des lieux de sortie s'appuie sur celui-ci : il ne se rouvre plus."})
    inspection.status, inspection.signed_at, inspection.signed_by = "DRAFT", None, None
    inspection.save(update_fields=["status", "signed_at", "signed_by"])
    return inspection


def faults(lease):
    """Ce qui est dégradé ou manquant à la sortie et ne l'était pas à l'entrée."""
    found = []
    items = InspectionItem.objects.filter(
        inspection__lease=lease, inspection__kind="EXIT", inspection__status="SIGNED", condition__in=InspectionItem.FAULTS
    ).select_related("reference")
    for item in items:
        if item.reference is None or item.reference.condition not in InspectionItem.FAULTS:
            found.append(item)
    return found
