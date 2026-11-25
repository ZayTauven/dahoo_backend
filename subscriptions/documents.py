"""Reçu d'abonnement remis par Dahoo à son client."""

from django.utils import timezone
from reportlab.lib.units import mm
from reportlab.platypus import Spacer
from rest_framework.exceptions import ValidationError

from dahoo.french import amount_in_words, long_date
from documents.pdf import BODY, MUTE, facts, header, lines, money, phone, render, text
from organizations.models import Organization
from subscriptions.models import BillingSettings


def _issuer():
    """L'organisation interne de Dahoo porte ses coordonnées et son logo."""
    return Organization.objects.filter(is_internal=True).order_by("pk").first() or Organization(name="Dahoo")


def _duration(payment):
    unit, count = ("an", payment.quantity) if payment.months == 12 else ("mois", payment.quantity)
    return f"{count} {unit}{'s' if unit == 'an' and count > 1 else ''}"


def subscription_receipt(payment):
    from documents.receipts import Document

    if payment.cancelled_at:
        raise ValidationError({"detail": "Ce règlement est annulé."})
    issuer, customer = _issuer(), payment.subscription.organization
    gross = payment.unit_price * payment.quantity
    rows = [[f"Offre {payment.plan_name}", _duration(payment), money(gross)]]
    if payment.credit:
        rows.append(["Reste de l'offre précédente", "", f"- {money(payment.credit)}"])
    if payment.discount:
        rows.append(["Remise", "", f"- {money(payment.discount)}"])

    story = header(issuer, title="Reçu d'abonnement", reference_number=payment.number, issued=long_date(timezone.localdate()))
    story += facts(
        ("Client", [customer.name, customer.city, phone(customer.phone)]),
        ("Période couverte", [f"du {payment.period_start:%d/%m/%Y}", f"au {payment.period_end:%d/%m/%Y}"]),
        ("Règlement", [payment.method.label, f"le {payment.paid_on:%d/%m/%Y}", payment.reference]),
    )
    story += lines(["Désignation", "Durée", "Montant"], rows, total=["Total réglé", "", money(payment.amount)], widths=[0.5, 0.2, 0.3])
    story += [text(f"Reçu de {customer.name} la somme de {amount_in_words(payment.amount)}.", BODY), Spacer(1, 4 * mm)]
    legal = BillingSettings.load().legal_notice.strip()
    if legal:
        story.append(text(legal, MUTE))
    content = render(f"Reçu {payment.number}", story, footer=issuer.name)
    return Document(f"recu-abonnement-{payment.number}.pdf", content)
