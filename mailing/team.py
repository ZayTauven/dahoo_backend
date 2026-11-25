"""E-mails de l'équipe : pannes confiées, fin d'essai, point du jour. Seules les adresses confirmées les reçoivent."""

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from analytics.dashboard import schedules_with_remaining
from dahoo.french import long_date
from deposits.services import deposits_to_return
from leases.models import LeaseContract
from leases.tenants import tenant_names
from mailing.queue import queue_email
from maintenance.models import MaintenanceTicket
from notifications.services import members_with, money
from payments.models import Payment

User = get_user_model()

DIGEST_ROWS = 5
ENDING_DAYS = 30


def site(path):
    return f"{settings.PUBLIC_SITE_URL}{path}"


def verified(users):
    return users.exclude(email="").filter(email__isnull=False, email_verified_at__isnull=False)


def ticket_context(ticket):
    unit = ticket.unit
    return {
        "unit": unit.reference, "property": unit.building.property.name,
        "category": ticket.category.label if ticket.category else "Maintenance",
        "priority": ticket.get_priority_display(), "description": ticket.description[:400],
        "url": site(f"/espace/maintenance/{ticket.pk}"),
    }


def email_ticket_created(ticket):
    """Panne prioritaire seulement : les autres sont dans le point du jour."""
    if ticket.priority not in ("HIGH", "URGENT"):
        return
    organization = ticket.unit.building.property.organization
    members = verified(members_with(organization, "maintenance.ticket.assign")).filter(email_alerts=True).exclude(pk=ticket.reported_by_id)
    for user in members:
        queue_email("ticket_created", user.email, {"first_name": user.first_name, **ticket_context(ticket)}, organization=organization)


def email_ticket_assigned(assignment):
    user = assignment.assigned_to
    if user.pk == assignment.assigned_by_id or not (user.email and user.email_verified_at and user.email_alerts):
        return
    ticket = assignment.ticket
    queue_email(
        "ticket_assigned", user.email,
        {"first_name": user.first_name, "author": f"{assignment.assigned_by.first_name} {assignment.assigned_by.last_name}".strip(), **ticket_context(ticket)},
        organization=ticket.unit.building.property.organization,
    )


def email_trial_ending(organization, ends):
    for user in verified(members_with(organization, "organization.update")):
        queue_email(
            "trial_ending", user.email,
            {"first_name": user.first_name, "organization": organization.name, "date": long_date(ends), "url": site("/espace/agence")},
            organization=organization, dedupe_key=f"trial:{organization.pk}:{user.pk}:{ends:%Y%m%d}",
        )


def build_digest(organization, capabilities, *, today):
    """Ce qui demande une action aujourd'hui, selon les droits du membre. Vide : pas d'e-mail."""
    name = tenant_names(organization)
    sections = []
    if "payment.schedule.view" in capabilities:
        overdue = {}
        for schedule in (
            schedules_with_remaining(organization)
            .filter(is_paid=False, remaining__gt=0, due_date__lt=today, lease_contract__isnull=False)
            .select_related("lease_contract__tenant", "lease_contract__unit").order_by("due_date")
        ):
            overdue.setdefault(schedule.lease_contract, []).append(schedule)
        if overdue:
            total = sum((s.remaining for group in overdue.values() for s in group), Decimal("0"))
            rows = sorted(overdue.items(), key=lambda item: -sum(s.remaining for s in item[1]))
            sections.append({
                "title": f"Loyers en retard : {money(total)}", "url": site("/espace/loyers?etat=LATE"), "more": max(0, len(rows) - DIGEST_ROWS),
                "rows": [
                    {"label": f"{name(lease.tenant)}, {lease.unit.reference}", "value": money(sum((s.remaining for s in group), Decimal("0")))}
                    for lease, group in rows[:DIGEST_ROWS]
                ],
            })
    if "payment.view" in capabilities:
        yesterday = today - timedelta(days=1)
        payments = list(
            Payment.objects.cash().filter(organization=organization, created_at__date=yesterday)
            .select_related("payer", "payment_method").order_by("-amount_paid")
        )
        if payments:
            total = sum((payment.amount_paid for payment in payments), Decimal("0"))
            sections.append({
                "title": f"Encaissé hier : {money(total)}", "url": site("/espace/paiements"), "more": max(0, len(payments) - DIGEST_ROWS),
                "rows": [{"label": f"{name(p.payer)}, {p.payment_method.label}", "value": money(p.amount_paid)} for p in payments[:DIGEST_ROWS]],
            })
    if "lease.view" in capabilities:
        ending = list(
            LeaseContract.objects.filter(
                organization=organization, status="ACTIVE", end_date__gte=today, end_date__lte=today + timedelta(days=ENDING_DAYS)
            ).select_related("tenant", "unit").order_by("end_date")
        )
        if ending:
            sections.append({
                "title": "Baux à renouveler", "url": site("/espace/baux"), "more": max(0, len(ending) - DIGEST_ROWS),
                "rows": [{"label": f"{name(lease.tenant)}, {lease.unit.reference}", "value": f"{lease.end_date:%d/%m/%Y}"} for lease in ending[:DIGEST_ROWS]],
            })
    if "deposit.view" in capabilities:
        rows = deposits_to_return(organization)
        if rows:
            sections.append({
                "title": f"Cautions à rendre : {money(sum((row['held'] for row in rows), Decimal('0')))}", "url": site("/espace/cautions"), "more": max(0, len(rows) - DIGEST_ROWS),
                "rows": [{"label": f"{row['tenant_name']}, {row['unit_reference']}", "value": money(row["held"])} for row in rows[:DIGEST_ROWS]],
            })
    if "maintenance.ticket.view" in capabilities:
        tickets = list(
            MaintenanceTicket.objects.filter(unit__building__property__organization=organization, status="OPEN")
            .select_related("unit", "category").order_by("-created_at")
        )
        if tickets:
            sections.append({
                "title": "Pannes à traiter", "url": site("/espace/maintenance"), "more": max(0, len(tickets) - DIGEST_ROWS),
                "rows": [
                    {"label": f"{t.category.label if t.category else 'Maintenance'}, {t.unit.reference}", "value": t.get_priority_display()}
                    for t in tickets[:DIGEST_ROWS]
                ],
            })
    return sections


def send_digests(organization, *, today=None):
    today = today or timezone.localdate()
    count = 0
    members = organization.memberships.filter(is_active=True, user__is_active=True, user__email_digest=True).select_related("user", "role")
    for membership in members:
        user = membership.user
        if not (user.email and user.email_verified_at):
            continue
        capabilities = set(membership.role.capabilities.values_list("code", flat=True))
        sections = build_digest(organization, capabilities, today=today)
        if sections and queue_email(
            "daily_digest", user.email,
            {"first_name": user.first_name, "organization": organization.name, "date": long_date(today), "sections": sections, "url": site("/espace")},
            organization=organization, dedupe_key=f"digest:{organization.pk}:{user.pk}:{today:%Y%m%d}",
        ):
            count += 1
    return count
