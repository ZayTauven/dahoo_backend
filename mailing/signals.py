"""Événements qui déclenchent un e-mail. Muets pendant les jeux de démo et les imports (notifications.signals.muted)."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from maintenance.models import MaintenanceAssignment, MaintenanceTicket
from notifications.signals import after_commit
from owners.models import OwnerPayout
from public.models import DemoRequest


@receiver(post_save, sender=MaintenanceTicket)
def ticket_created(sender, instance, created, **kwargs):
    if created:
        from mailing.team import email_ticket_created

        after_commit(lambda: email_ticket_created(instance))


@receiver(post_save, sender=MaintenanceAssignment)
def ticket_assigned(sender, instance, created, **kwargs):
    if created:
        from mailing.team import email_ticket_assigned

        after_commit(lambda: email_ticket_assigned(instance))


@receiver(post_save, sender=OwnerPayout)
def payout_recorded(sender, instance, created, **kwargs):
    if created and instance.organization.email_owner_payouts:
        from mailing.agency import email_payout

        after_commit(lambda: email_payout(instance))


@receiver(post_save, sender=DemoRequest)
def demo_requested(sender, instance, created, **kwargs):
    if created:
        from mailing.platform import email_demo_request

        after_commit(lambda: email_demo_request(instance))
