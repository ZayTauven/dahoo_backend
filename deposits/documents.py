"""Décompte de restitution de caution remis au locataire."""

from django.utils import timezone
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Spacer
from rest_framework.exceptions import ValidationError

from dahoo.french import amount_in_words, long_date
from dahoo.whatsapp import whatsapp_url
from documents.pdf import BODY, MUTE, facts, header, lines, money, phone, render, text
from inspections.report import signatures
from leases.tenants import tenant_names


def settlement_report(settlement):
    from documents.receipts import Document

    if settlement.cancelled_at:
        raise ValidationError({"detail": "Ce décompte est annulé."})
    lease, organization = settlement.lease, settlement.organization
    unit = lease.unit
    tenant = tenant_names(organization)(lease.tenant)
    story = header(organization, title="Décompte de caution", reference_number=settlement.number, issued=long_date(timezone.localdate()))
    story += facts(
        ("Locataire", [tenant, phone(lease.tenant.phone)]),
        ("Logement", [unit.reference, unit.building.property.name]),
        ("Bail", [f"du {lease.start_date:%d/%m/%Y}", f"au {lease.ended_on:%d/%m/%Y}" if lease.ended_on else ""]),
    )
    rows = [["Caution détenue", money(settlement.held_amount)]]
    if settlement.rent_payment:
        for allocation in settlement.rent_payment.allocations.select_related("schedule").order_by("schedule__due_date", "id"):
            rows.append([f"{allocation.schedule.get_schedule_type_display()}, échéance du {allocation.schedule.due_date:%d/%m/%Y}", f"- {money(allocation.allocated_amount)}"])
    for deduction in settlement.deductions.all():
        rows.append([f"{deduction.get_kind_display()} : {deduction.label}", f"- {money(deduction.amount)}"])
    story += lines(["Désignation", "Montant"], rows, total=["Montant rendu", money(settlement.refund_amount)], widths=[0.7, 0.3])
    if settlement.refund_amount > 0:
        reference = f", référence {settlement.reference}" if settlement.reference else ""
        story.append(text(f"Rendu à {tenant} la somme de {amount_in_words(settlement.refund_amount)}, par {settlement.method.label.lower()} le {long_date(settlement.settled_on)}{reference}.", BODY))
    else:
        story.append(text("La caution est entièrement retenue : aucune somme n'est rendue.", BODY))
    if settlement.note:
        story += [Spacer(1, 4 * mm), text(settlement.note, BODY)]
    story.append(KeepTogether([
        Spacer(1, 8 * mm), text("Les parties reconnaissent avoir pris connaissance de ce décompte.", MUTE), Spacer(1, 3 * mm),
        signatures(f"Pour {organization.name}", f"Le locataire : {tenant}"),
    ]))
    content = render(f"Décompte {settlement.number}", story, footer=organization.name)
    return Document(f"decompte-caution-{settlement.number}.pdf", content)


def share_settlement(settlement):
    from documents.receipts import share_url

    if settlement.cancelled_at:
        raise ValidationError({"detail": "Ce décompte est annulé."})
    organization, lease = settlement.organization, settlement.lease
    url = share_url("deposit", settlement.pk)
    name = tenant_names(organization)(lease.tenant)
    amount = money(settlement.refund_amount).replace("\u00a0", " ")
    message = f"Bonjour {name}, voici le décompte de votre caution ({amount} rendus) : {url}\n{organization.name}"
    return {"url": url, "message": message, "whatsapp_url": whatsapp_url(lease.tenant.phone, message)}
