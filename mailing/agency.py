"""E-mails envoyés pour le compte d'une agence à ses locataires et à ses bailleurs."""

from rest_framework.exceptions import ValidationError

from dahoo.french import long_date, month_label
from deposits.documents import share_settlement
from documents.receipts import period_label, share_payment_receipt, share_rent_receipt, share_statement
from leases.models import Tenant
from leases.tenants import tenant_names
from mailing.addresses import is_deliverable
from mailing.queue import queue_email
from notifications.services import money
from owners.statements import build_statement


def tenant_email(organization, user):
    """Adresse saisie par l'agence sur SA fiche locataire (jamais celle du compte partagé)."""
    return Tenant.objects.filter(organization=organization, user=user).values_list("email", flat=True).first() or ""


def _require(email, who):
    if not is_deliverable(email):
        raise ValidationError({"detail": f"Aucune adresse e-mail utilisable pour ce {who}."})


def _lease_context(lease):
    return {
        "name": tenant_names(lease.organization)(lease.tenant),
        "unit": lease.unit.reference,
        "property": lease.unit.building.property.name,
    }


def email_rent_receipt(schedule, *, strict=True, dedupe_key=""):
    lease = schedule.lease_contract
    to = tenant_email(schedule.organization, lease.tenant)
    if strict:
        _require(to, "locataire")
    share = share_rent_receipt(schedule)
    return queue_email("rent_receipt", to, {
        **_lease_context(lease), "period": period_label(schedule), "amount": money(schedule.amount_due), "url": share["url"],
    }, organization=schedule.organization, dedupe_key=dedupe_key)


def email_payment_receipt(payment, *, strict=True, dedupe_key=""):
    to = tenant_email(payment.organization, payment.payer)
    if strict:
        _require(to, "locataire")
    share = share_payment_receipt(payment)
    return queue_email("payment_receipt", to, {
        "name": tenant_names(payment.organization)(payment.payer), "amount": money(payment.amount_paid),
        "method": payment.payment_method.label, "date": long_date(payment.payment_date.date()),
        "reference": payment.reference or "", "url": share["url"],
    }, organization=payment.organization, dedupe_key=dedupe_key)


def email_payment_documents(payment, **options):
    """Le bon document après un encaissement : la quittance de chaque loyer soldé, sinon le reçu."""
    settled = [
        allocation.schedule
        for allocation in payment.allocations.select_related(
            "schedule__organization", "schedule__lease_contract__tenant", "schedule__lease_contract__unit__building__property__owner"
        )
        if allocation.schedule.is_paid and allocation.schedule.schedule_type in ("RENT", "CHARGE")
    ]
    if not settled:
        return [email_payment_receipt(payment, **options)]
    return [email_rent_receipt(schedule, **options) for schedule in settled]


def email_rent_due(schedule, remaining, *, dedupe_key):
    lease = schedule.lease_contract
    return queue_email("rent_due", tenant_email(schedule.organization, lease.tenant), {
        **_lease_context(lease), "amount": money(remaining), "date": long_date(schedule.due_date),
    }, organization=schedule.organization, dedupe_key=dedupe_key)


def email_rent_overdue(lease, reminder, *, strict=True, dedupe_key=""):
    """`reminder` : résultat de payments.reminders.reminder_for (montant dû, nombre d'échéances)."""
    to = tenant_email(lease.organization, lease.tenant)
    if strict:
        _require(to, "locataire")
    return queue_email("rent_overdue", to, {
        **_lease_context(lease), "amount": money(reminder["amount"]), "count": reminder["count"],
        "since": long_date(reminder["since"]),
    }, organization=lease.organization, dedupe_key=dedupe_key)


def email_deposit_settlement(settlement):
    lease = settlement.lease
    to = tenant_email(settlement.organization, lease.tenant)
    _require(to, "locataire")
    return queue_email("deposit_settlement", to, {
        **_lease_context(lease), "held": money(settlement.held_amount), "retained": money(settlement.held_amount - settlement.refund_amount),
        "refund": money(settlement.refund_amount), "url": share_settlement(settlement)["url"],
    }, organization=settlement.organization)


def email_statement(owner, month):
    _require(owner.email, "bailleur")
    data = build_statement(owner, month=month)
    return queue_email("owner_statement", owner.email, {
        "name": owner.full_name, "month": month_label(month), "collected": money(data["collected"]),
        "commission": money(data["commission"]), "expenses": money(data["expenses"]),
        "balance": money(data["closing_balance"]), "url": share_statement(owner, month)["url"],
    }, organization=owner.organization)


def email_payout(payout):
    owner = payout.owner
    return queue_email("owner_payout", owner.email, {
        "name": owner.full_name, "amount": money(payout.amount), "date": long_date(payout.paid_on),
        "channel": payout.get_channel_display(), "reference": payout.reference,
    }, organization=payout.organization, dedupe_key=f"payout:{payout.pk}")
