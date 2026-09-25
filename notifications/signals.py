"""
Événements notifiés dans l'espace connecté. Les notifications sont créées après la validation de la
transaction (on_commit) et une erreur est seulement journalisée : notifier ne doit jamais empêcher
d'enregistrer un paiement ou un ticket.
"""

import logging
from contextlib import contextmanager
from contextvars import ContextVar

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from listings.models import ProspectInterest
from maintenance.models import MaintenanceAssignment, MaintenanceTicket
from payments.models import Payment
from public.models import DemoRequest

from . import services

logger = logging.getLogger(__name__)


_muted = ContextVar("notifications_muted", default=False)


@contextmanager
def muted():
    """Suspend les notifications d'événements (jeux de démo, imports en masse)."""
    token = _muted.set(True)
    try:
        yield
    finally:
        _muted.reset(token)


def _after_commit(callback):
    if _muted.get():
        return

    def run():
        try:
            callback()
        except Exception:  # noqa: BLE001 — une notification manquée ne doit rien casser
            logger.exception("Notification non créée")

    transaction.on_commit(run)


def _unit_organization(unit):
    return unit.building.property.organization


@receiver(post_save, sender=ProspectInterest)
def visit_requested(sender, instance, created, **kwargs):
    if not created:
        return

    def notify():
        listing = instance.listing
        message = instance.message.strip()
        services.notify_members(
            _unit_organization(listing.unit),
            capability="listing.interest.view",
            kind="VISIT_REQUEST",
            title=f"Demande de visite : {listing.title}",
            body=f"{instance.prospect.full_name} · {message[:140]}" if message else instance.prospect.full_name,
            link=f"/espace/annonces/{listing.pk}",
        )

    _after_commit(notify)


@receiver(post_save, sender=Payment)
def payment_recorded(sender, instance, created, **kwargs):
    if not created:
        return

    def notify():
        payer = services.person_name(instance.payer)
        services.notify_members(
            instance.organization,
            capability="payment.view",
            kind="PAYMENT_RECEIVED",
            title=f"Paiement de {services.money(instance.amount_paid)}",
            body=" · ".join(part for part in (payer, instance.payment_method.label) if part),
            link="/espace/paiements",
            exclude=instance.recorded_by,
        )

    _after_commit(notify)


PRIORITY_PREFIX = {"URGENT": "Urgent · ", "HIGH": "Priorité haute · "}


@receiver(post_save, sender=MaintenanceTicket)
def ticket_created(sender, instance, created, **kwargs):
    if not created:
        return

    def notify():
        category = instance.category.label if instance.category else "Maintenance"
        services.notify_members(
            _unit_organization(instance.unit),
            capability="maintenance.ticket.view",
            kind="TICKET_CREATED",
            title=f"{PRIORITY_PREFIX.get(instance.priority, '')}{category} : {instance.unit.reference}",
            body=instance.description[:160],
            link=f"/espace/maintenance/{instance.pk}",
            exclude=instance.reported_by,
        )

    _after_commit(notify)


@receiver(post_save, sender=MaintenanceAssignment)
def ticket_assigned(sender, instance, created, **kwargs):
    if not created or instance.assigned_to_id == instance.assigned_by_id:
        return

    def notify():
        ticket = instance.ticket
        services.notify_user(
            instance.assigned_to,
            organization=_unit_organization(ticket.unit),
            kind="TICKET_ASSIGNED",
            title=f"Ticket assigné : {ticket.unit.reference}",
            body=" · ".join(
                part for part in (f"Par {services.person_name(instance.assigned_by)}" if instance.assigned_by_id else "", ticket.description[:120]) if part
            ),
            link=f"/espace/maintenance/{ticket.pk}",
        )

    _after_commit(notify)


@receiver(post_save, sender=DemoRequest)
def demo_requested(sender, instance, created, **kwargs):
    if not created:
        return

    def notify():
        details = [instance.contact_name, instance.city, f"{instance.units_range} lots"]
        services.notify_platform_admins(
            kind="DEMO_REQUEST",
            title=f"Demande de démo : {instance.agency_name}",
            body=" · ".join(part for part in details if part),
            link="/plateforme/demandes",
        )

    _after_commit(notify)
