"""
Documents remis par l'agence : quittance de loyer, reçu de paiement, relevé de gestion.

Chaque document est fabriqué à la demande à partir des écritures. Un lien de partage signé permet de
l'envoyer par WhatsApp à une personne sans compte ; il cesse de fonctionner si l'écriture est annulée.
"""

from dataclasses import dataclass

from django.conf import settings
from django.core import signing
from django.shortcuts import get_object_or_404
from django.utils import timezone
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Spacer
from rest_framework.exceptions import NotFound, ValidationError

from dahoo.french import amount_in_words, long_date, month_label
from dahoo.whatsapp import whatsapp_url
from documents.pdf import BODY, MUTE, SECTION, facts, header, lines, money, number as plain, phone, render, text
from leases.tenants import tenant_names
from owners.models import Owner
from owners.statements import build_statement
from payments.models import Payment, PaymentSchedule
from payments.schedules import period_months, schedule_period

SALT = "dahoo.documents"


@dataclass(frozen=True)
class Document:
    filename: str
    content: bytes


def _managed_for(lease):
    owner = lease.unit.building.property.owner
    return f"Pour le compte de {owner.full_name}, bailleur" if owner else ""


def _place(lease):
    prop = lease.unit.building.property
    return [lease.unit.reference, prop.name, ", ".join(part for part in (prop.neighborhood, prop.city) if part)]


def period_label(schedule):
    first, last = schedule_period(schedule)
    if (first.year, first.month) == (last.year, last.month):
        return month_label(first)
    return f"{month_label(first)} à {month_label(last)}"


def _schedule_title(schedule):
    if schedule.schedule_type in ("DEPOSIT", "ARREARS"):
        return schedule.get_schedule_type_display()
    return f"{schedule.get_schedule_type_display()} · {period_label(schedule)}"


def _payment_rows(allocations):
    return [
        [f"{allocation.payment.payment_date:%d/%m/%Y}", allocation.payment.payment_method.label, allocation.payment.reference or "", money(allocation.allocated_amount)]
        for allocation in allocations
    ]


# --- Quittance de loyer


def rent_schedules():
    return PaymentSchedule.objects.select_related(
        "organization", "lease_contract__tenant", "lease_contract__unit__building__property__owner"
    ).filter(lease_contract__isnull=False)


def check_receipt(schedule):
    """Une quittance vaut solde de la période : elle n'existe que pour un loyer entièrement réglé."""
    if schedule.schedule_type not in ("RENT", "CHARGE"):
        raise ValidationError({"detail": "La quittance ne concerne que les loyers et les charges."})
    if not schedule.is_paid:
        raise ValidationError({"detail": "Cette échéance n'est pas soldée : remettez le reçu du paiement."})


def rent_receipt(schedule):
    check_receipt(schedule)
    lease, organization = schedule.lease_contract, schedule.organization
    tenant = tenant_names(organization)(lease.tenant)
    first, last = schedule_period(schedule)
    number = f"Q{schedule.due_date:%Y%m}-{schedule.pk}"
    allocations = list(schedule.allocations.select_related("payment__payment_method").order_by("payment__payment_date", "id"))

    months = period_months(lease)
    charges = lease.charges_amount * months
    if schedule.schedule_type == "RENT" and charges and schedule.amount_due == (lease.rent_amount + lease.charges_amount) * months:
        detail = [["Loyer", money(lease.rent_amount * months)], ["Charges", money(charges)]]
    else:
        detail = [[schedule.get_schedule_type_display() + (", charges comprises" if charges and schedule.schedule_type == "RENT" else ""), money(schedule.amount_due)]]

    story = header(organization, title="Quittance de loyer", reference_number=number, issued=long_date(timezone.localdate()))
    story += facts(
        ("Locataire", [tenant, phone(lease.tenant.phone)]),
        ("Logement", _place(lease)),
        ("Période", [period_label(schedule), f"du {first:%d/%m/%Y} au {last:%d/%m/%Y}"]),
    )
    story += lines(["Désignation", "Montant"], detail, total=["Total réglé", money(schedule.amount_due)], widths=[0.7, 0.3])
    story += [
        text(f"Reçu de {tenant} la somme de {amount_in_words(schedule.amount_due)}, pour le loyer du logement désigné ci-dessus.", BODY),
        Spacer(1, 6 * mm),
        text("Règlements", SECTION),
        Spacer(1, 2 * mm),
    ]
    story += lines(["Date", "Moyen", "Référence", "Montant"], _payment_rows(allocations), widths=[0.2, 0.28, 0.27, 0.25])
    if _managed_for(lease):
        story.append(text(_managed_for(lease), MUTE))
    story.append(text("Cette quittance annule les reçus remis pour la même période et ne préjuge pas des autres sommes dues.", MUTE))
    content = render(f"Quittance {number}", story, footer=organization.name)
    return Document(f"quittance-{number}.pdf", content)


# --- Reçu de paiement


def payment_receipt(payment):
    if payment.cancelled_at:
        raise ValidationError({"detail": "Ce paiement est annulé."})
    organization = payment.organization
    payer = tenant_names(organization)(payment.payer)
    number = f"R{payment.payment_date:%Y%m}-{payment.pk}"
    allocations = list(
        payment.allocations.select_related("schedule__lease_contract__unit__building__property__owner", "schedule__lease_contract__tenant").order_by("schedule__due_date", "id")
    )
    rows = [
        [_schedule_title(a.schedule) if a.schedule.lease_contract_id else "Vente", a.schedule.lease_contract.unit.reference if a.schedule.lease_contract_id else "", money(a.allocated_amount)]
        for a in allocations
    ]
    advance = payment.amount_paid - sum((a.allocated_amount for a in allocations), 0)
    if advance > 0:
        rows.append(["Avance sur les prochaines échéances" if rows else "Paiement", "", money(advance)])
    story = header(organization, title="Reçu de paiement", reference_number=number, issued=long_date(timezone.localdate()))
    story += facts(
        ("Reçu de", [payer, phone(payment.payer.phone)]),
        ("Date", [long_date(timezone.localtime(payment.payment_date).date())]),
        ("Moyen", [payment.payment_method.label, payment.reference or ""]),
    )
    story += lines(["Affectation", "Lot", "Montant"], rows, total=["Total reçu", "", money(payment.amount_paid)], widths=[0.5, 0.2, 0.3])
    story += [text(f"Reçu la somme de {amount_in_words(payment.amount_paid)}.", BODY), Spacer(1, 4 * mm)]
    partial = [a.schedule for a in allocations if not a.schedule.is_paid]
    if partial:
        story.append(text("Paiement partiel : ce reçu ne vaut pas quittance.", MUTE))
    content = render(f"Reçu {number}", story, footer=organization.name)
    return Document(f"recu-{number}.pdf", content)


# --- Relevé de gestion


def owner_statement(owner, month):
    organization = owner.organization
    data = build_statement(owner, month=month)
    number = f"G{data['month']:%Y%m}-{owner.pk}"
    story = header(organization, title="Relevé de gestion", reference_number=number, issued=long_date(timezone.localdate()))
    story += facts(
        ("Bailleur", [owner.full_name, phone(owner.user.phone)]),
        ("Période", [month_label(data["month"])]),
        ("Solde à reverser", [money(data["closing_balance"])]),
    )
    if data["units"]:
        story += lines(
            ["Lot", "Locataire", "Appelé", "Encaissé", "Impayé", "Commission"],
            [
                [f"{row['unit_reference']} · {row['property_name']}", row["tenant_name"], plain(row["expected"]), plain(row["collected"]), plain(row["unpaid"]), plain(row["commission"])]
                for row in data["units"]
            ],
            total=["Total (F CFA)", "", plain(data["expected"]), plain(data["collected"]), plain(data["unpaid"]), plain(data["commission"])],
            widths=[0.32, 0.18, 0.125, 0.125, 0.125, 0.125], numeric=4,
        )
    else:
        story += [text("Aucun loyer sur la période."), Spacer(1, 5 * mm)]
    if data["expense_lines"]:
        story += [text("Dépenses", SECTION), Spacer(1, 2 * mm)]
        story += lines(
            ["Date", "Objet", "Bien", "Montant"],
            [[f"{e['date']:%d/%m/%Y}", e["label"], " · ".join(p for p in (e["property_name"], e["unit_reference"]) if p), money(e["amount"])] for e in data["expense_lines"]],
            widths=[0.16, 0.34, 0.28, 0.22],
        )
    if data["retention_lines"]:
        story += [text("Retenues sur cautions", SECTION), Spacer(1, 2 * mm)]
        story += lines(
            ["Date", "Objet", "Bien", "Montant"],
            [[f"{e['date']:%d/%m/%Y}", e["label"], f"{e['property_name']} · {e['unit_reference']}", money(e["amount"])] for e in data["retention_lines"]],
            widths=[0.16, 0.34, 0.28, 0.22],
        )
    if data["payout_lines"]:
        story += [text("Reversements", SECTION), Spacer(1, 2 * mm)]
        story += lines(
            ["Date", "Moyen", "Référence", "Montant"],
            [[f"{p['date']:%d/%m/%Y}", p["channel"], p["reference"], money(p["amount"])] for p in data["payout_lines"]],
            widths=[0.16, 0.34, 0.28, 0.22],
        )
    # La synthèse reste d'un bloc : elle ne se coupe pas entre deux pages.
    summary = [text("Synthèse", SECTION), Spacer(1, 2 * mm)]
    summary += lines(
        ["", "Montant"],
        [
            ["Solde précédent", money(data["opening_balance"])],
            ["Loyers et charges encaissés", money(data["collected"])],
            ["Commission de gestion", f"- {money(data['commission'])}"],
            *([["Retenues sur cautions", money(data["retentions"])]] if data["retentions"] else []),
            ["Dépenses", f"- {money(data['expenses'])}"],
            ["Reversements effectués", f"- {money(data['payouts'])}"],
        ],
        total=["Solde à reverser", money(data["closing_balance"])], widths=[0.7, 0.3],
    )
    story.append(KeepTogether(summary))
    content = render(f"Relevé {number}", story, footer=organization.name)
    return Document(f"releve-{number}.pdf", content)


# --- Partage par lien signé


def _token(kind, pk, **extra):
    return signing.dumps({"k": kind, "i": pk, **extra}, salt=SALT, compress=True)


def share_url(kind, pk, **extra):
    return f"{settings.PUBLIC_SITE_URL}/d/{_token(kind, pk, **extra)}"


def document_from_token(token):
    try:
        data = signing.loads(token, salt=SALT, max_age=settings.DOCUMENT_LINK_MAX_AGE)
    except signing.BadSignature:
        raise NotFound("Ce lien n'est pas valide ou a expiré.")
    kind, pk = data.get("k"), data.get("i")
    try:
        if kind == "rent":
            return rent_receipt(get_object_or_404(rent_schedules(), pk=pk))
        if kind == "payment":
            return payment_receipt(get_object_or_404(Payment.objects.select_related("organization", "payer", "payment_method"), pk=pk))
        if kind == "inspection":
            from inspections.models import Inspection
            from inspections.report import inspection_report

            # Rouvert pour correction : le lien envoyé ne montre pas un document en cours.
            return inspection_report(get_object_or_404(
                Inspection.objects.select_related("organization", "lease__tenant", "lease__unit__building__property"), pk=pk, status="SIGNED"
            ))
        if kind == "deposit":
            from deposits.documents import settlement_report
            from deposits.models import DepositSettlement

            return settlement_report(get_object_or_404(
                DepositSettlement.objects.select_related("organization", "method", "rent_payment", "lease__tenant", "lease__unit__building__property"), pk=pk
            ))
        if kind == "subscription":
            from subscriptions.documents import subscription_receipt
            from subscriptions.models import SubscriptionPayment

            return subscription_receipt(get_object_or_404(SubscriptionPayment.objects.select_related("subscription__organization", "method"), pk=pk))
        if kind == "statement":
            year, month = data["m"].split("-")
            owner = get_object_or_404(Owner.objects.select_related("organization", "user"), pk=pk)
            return owner_statement(owner, timezone.datetime(int(year), int(month), 1).date())
    except ValidationError:
        raise NotFound("Ce document n'est plus disponible.")
    raise NotFound("Ce lien n'est pas valide ou a expiré.")


def _share(phone, message, url):
    return {"url": url, "message": message, "whatsapp_url": whatsapp_url(phone, message)}


def share_rent_receipt(schedule):
    check_receipt(schedule)
    lease, organization = schedule.lease_contract, schedule.organization
    url = share_url("rent", schedule.pk)
    name = tenant_names(organization)(lease.tenant)
    message = f"Bonjour {name}, voici votre quittance de loyer ({period_label(schedule)}) : {url}\n{organization.name}"
    return _share(lease.tenant.phone, message, url)


def share_payment_receipt(payment):
    if payment.cancelled_at:
        raise ValidationError({"detail": "Ce paiement est annulé."})
    organization = payment.organization
    url = share_url("payment", payment.pk)
    name = tenant_names(organization)(payment.payer)
    amount = money(payment.amount_paid).replace("\u00a0", " ")
    message = f"Bonjour {name}, nous avons bien reçu votre paiement de {amount}. Votre reçu : {url}\n{organization.name}"
    return _share(payment.payer.phone, message, url)


def share_statement(owner, month):
    url = share_url("statement", owner.pk, m=f"{month:%Y-%m}")
    message = f"Bonjour {owner.full_name}, voici votre relevé de gestion de {month_label(month)} : {url}\n{owner.organization.name}"
    return _share(owner.user.phone, message, url)
