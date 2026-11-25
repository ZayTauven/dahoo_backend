"""État des lieux en PDF : éléments par pièce, comparaison à la sortie, photos et cadres de signature."""

from itertools import groupby

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, KeepTogether, Spacer, Table, TableStyle

from dahoo.french import long_date
from dahoo.whatsapp import whatsapp_url
from documents.pdf import BODY, LINE, MUTE, SECTION, WIDTH, facts, header, lines, phone, render, text
from leases.tenants import tenant_names
from rest_framework.exceptions import ValidationError

PHOTOS_PER_ROW = 4
MAX_REPORT_PHOTOS = 60


def signatures(*names):
    """Cadres à signer, côte à côte."""
    share = WIDTH / len(names)
    table = Table([[text(name, MUTE) for name in names]], colWidths=[share] * len(names), rowHeights=[28 * mm])
    table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, LINE), ("INNERGRID", (0, 0), (-1, -1), 0.6, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 6), ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return table


def _thumbnail(photo):
    try:
        with photo.image.open("rb") as file:
            width, height = ImageReader(file).getSize()
        # Chemin de fichier : ReportLab lit l'image à la demande, sans tout garder en mémoire.
        side = WIDTH / PHOTOS_PER_ROW - 4 * mm
        ratio = min(side / width, 34 * mm / height)
        return Image(photo.image.path, width=width * ratio, height=height * ratio)
    except Exception:  # noqa: BLE001 - une photo perdue n'empêche pas d'émettre le document
        return None


def _photos(photos):
    cells = []
    for photo in photos[:MAX_REPORT_PHOTOS]:
        image = _thumbnail(photo)
        if image:
            label = f"{photo.item.room}, {photo.item.label}" if photo.item else "Vue générale"
            cells.append([image, text(label, MUTE)])
    if not cells:
        return []
    rows = [cells[i:i + PHOTOS_PER_ROW] for i in range(0, len(cells), PHOTOS_PER_ROW)]
    rows[-1] += [""] * (PHOTOS_PER_ROW - len(rows[-1]))
    table = Table(rows, colWidths=[WIDTH / PHOTOS_PER_ROW] * PHOTOS_PER_ROW)
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 8), ("TEXTCOLOR", (0, 0), (-1, -1), colors.black)]))
    return [text("Photos", SECTION), Spacer(1, 3 * mm), table]


def inspection_report(inspection):
    from documents.receipts import Document

    lease, organization = inspection.lease, inspection.organization
    unit = lease.unit
    prop = unit.building.property
    tenant = tenant_names(organization)(lease.tenant)
    exit_ = inspection.kind == "EXIT"
    story = header(
        organization, title=f"État des lieux {'de sortie' if exit_ else 'd’entrée'}".replace("’", "'"),
        reference_number=inspection.number, issued=long_date(timezone.localdate()),
    )
    story += facts(
        ("Locataire", [tenant, phone(lease.tenant.phone)]),
        ("Logement", [unit.reference, prop.name, ", ".join(p for p in (prop.neighborhood, prop.city) if p)]),
        ("Fait le", [long_date(inspection.done_on), "Document de travail, non validé" if inspection.status == "DRAFT" else ""]),
    )
    story += facts(
        ("Compteur électrique", [inspection.electricity_reading or "Non relevé"]),
        ("Compteur d'eau", [inspection.water_reading or "Non relevé"]),
        ("Clés", [str(inspection.keys_count) if inspection.keys_count is not None else "Non comptées"]),
    )
    items = list(inspection.items.select_related("reference"))
    for room, group in groupby(items, key=lambda item: item.room):
        if exit_:
            rows = [
                [item.label, item.reference.get_condition_display() if item.reference else "", item.get_condition_display() or "À regarder", item.note]
                for item in group
            ]
            table = lines(["Élément", "Entrée", "Sortie", "Observation"], rows, widths=[0.28, 0.14, 0.14, 0.44], numeric=0)
        else:
            rows = [[item.label, item.get_condition_display() or "À regarder", item.note] for item in group]
            table = lines(["Élément", "État", "Observation"], rows, widths=[0.32, 0.16, 0.52], numeric=0)
        # Le titre d'une pièce ne reste jamais seul en bas de page.
        story.append(KeepTogether([text(room, SECTION), Spacer(1, 1 * mm), *table]))
    if inspection.note:
        story += [text("Observations générales", SECTION), Spacer(1, 1 * mm), text(inspection.note, BODY), Spacer(1, 5 * mm)]
    if inspection.tenant_remarks:
        story += [text("Réserves du locataire", SECTION), Spacer(1, 1 * mm), text(inspection.tenant_remarks, BODY), Spacer(1, 5 * mm)]
    story += _photos(list(inspection.photos.select_related("item")))
    story.append(KeepTogether([
        Spacer(1, 5 * mm),
        text(f"Établi contradictoirement le {long_date(inspection.done_on)}." if inspection.status == "SIGNED" else "À valider avec le locataire.", MUTE),
        Spacer(1, 3 * mm),
        signatures(f"Pour {organization.name}", f"Le locataire : {inspection.tenant_signer or tenant}"),
    ]))
    content = render(f"État des lieux {inspection.number}", story, footer=organization.name)
    return Document(f"etat-des-lieux-{inspection.number}.pdf", content)


def share_inspection(inspection):
    from documents.receipts import share_url

    if inspection.status != "SIGNED":
        raise ValidationError({"detail": "Validez l'état des lieux avant de l'envoyer."})
    organization, lease = inspection.organization, inspection.lease
    name = tenant_names(organization)(lease.tenant)
    url = share_url("inspection", inspection.pk)
    kind = "de sortie" if inspection.kind == "EXIT" else "d'entrée"
    message = f"Bonjour {name}, voici l'état des lieux {kind} du logement {lease.unit.reference} : {url}\n{organization.name}"
    return {"url": url, "message": message, "whatsapp_url": whatsapp_url(lease.tenant.phone, message)}
