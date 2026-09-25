"""
Fil de notifications de démonstration, tiré des vraies données de démo et daté de façon réaliste :
demandes de visite, paiements et tickets récents de Teranga, rappels du jour (retards, fins de bail),
et côté plateforme les dernières demandes de démo. Les plus anciennes sont déjà lues.
"""

from datetime import datetime, time, timedelta

from django.db.models import Max
from django.utils import timezone

from listings.models import ProspectInterest
from maintenance.models import MaintenanceTicket
from notifications import services
from notifications.models import InAppNotification
from payments.models import Payment
from public.models import DemoRequest


def _backdate(before_id, when, *, read):
    InAppNotification.objects.filter(id__gt=before_id).update(created_at=when, read=read)


def _last_id():
    return InAppNotification.objects.aggregate(last=Max("id"))["last"] or 0


def _event(when, now, notify):
    before = _last_id()
    notify()
    _backdate(before, when, read=now - when > timedelta(days=1))


def seed_notifications(organization):
    now = timezone.now()
    InAppNotification.objects.filter(organization=organization).delete()
    InAppNotification.objects.filter(organization__isnull=True).delete()

    ages = [timedelta(minutes=25), timedelta(hours=3), timedelta(days=1, hours=2)]
    interests = ProspectInterest.objects.filter(listing__unit__building__property__organization=organization)
    for age, interest in zip(ages, interests.select_related("listing", "prospect").order_by("-created_at")):
        listing = interest.listing
        _event(now - age, now, lambda listing=listing, interest=interest: services.notify_members(
            organization, capability="listing.interest.view", kind="VISIT_REQUEST",
            title=f"Demande de visite : {listing.title}",
            body=f"{interest.prospect.full_name} · {interest.message[:140]}".rstrip(" ·"),
            link=f"/espace/annonces/{listing.pk}",
        ))

    ages = [timedelta(hours=1, minutes=10), timedelta(days=2, hours=4)]
    payments = Payment.objects.filter(organization=organization).select_related("payer", "payment_method")
    for age, payment in zip(ages, payments.order_by("-payment_date")):
        _event(now - age, now, lambda payment=payment: services.notify_members(
            organization, capability="payment.view", kind="PAYMENT_RECEIVED",
            title=f"Paiement de {services.money(payment.amount_paid)}",
            body=f"{services.person_name(payment.payer)} · {payment.payment_method.label}",
            link="/espace/paiements",
        ))

    ages = [timedelta(hours=5), timedelta(days=3)]
    tickets = MaintenanceTicket.objects.filter(unit__building__property__organization=organization, status="OPEN")
    rank = {"URGENT": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    recent = sorted(tickets.select_related("unit", "category").order_by("-created_at")[:10], key=lambda t: rank[t.priority])
    for age, ticket in zip(ages, recent):
        category = ticket.category.label if ticket.category else "Maintenance"
        prefix = {"URGENT": "Urgent · ", "HIGH": "Priorité haute · "}.get(ticket.priority, "")
        _event(now - age, now, lambda ticket=ticket, category=category, prefix=prefix: services.notify_members(
            organization, capability="maintenance.ticket.view", kind="TICKET_CREATED",
            title=f"{prefix}{category} : {ticket.unit.reference}",
            body=ticket.description[:160],
            link=f"/espace/maintenance/{ticket.pk}",
        ))

    # Rappels du jour, comme si la tâche quotidienne était passée ce matin.
    morning = timezone.make_aware(datetime.combine(timezone.localdate(), time(7, 30)))
    before = _last_id()
    services.sync_reminders(organization, force=True)
    _backdate(before, min(morning, now - timedelta(minutes=5)), read=False)

    # Plateforme : les demandes de démo reçues ces derniers jours.
    for request in DemoRequest.objects.filter(created_at__gte=now - timedelta(days=10)).order_by("created_at"):
        before = _last_id()
        services.notify_platform_admins(
            kind="DEMO_REQUEST",
            title=f"Demande de démo : {request.agency_name}",
            body=" · ".join(part for part in (request.contact_name, request.city, f"{request.units_range} lots") if part),
            link="/plateforme/demandes",
        )
        _backdate(before, request.created_at, read=request.handled)
    services.sync_platform_reminders(force=True)
