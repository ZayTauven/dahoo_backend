from django.core.management.base import BaseCommand

from notifications.services import sync_platform_reminders, sync_reminders
from organizations.models import Organization


class Command(BaseCommand):
    help = "Crée les rappels (loyers en retard, fins de bail, fins d'essai) : à planifier une fois par jour."

    def handle(self, *args, **options):
        organizations = Organization.objects.filter(is_active=True)
        for organization in organizations:
            sync_reminders(organization, force=True)
        sync_platform_reminders(force=True)
        self.stdout.write(self.style.SUCCESS(f"Rappels à jour pour {organizations.count()} agence(s)."))
