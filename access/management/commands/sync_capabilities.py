from django.core.management.base import BaseCommand

from access.services import sync_capabilities


class Command(BaseCommand):
    help = "Synchronise les capabilities et les rôles système avec access/catalog.py."

    def handle(self, *args, **options):
        sync_capabilities()
        self.stdout.write(self.style.SUCCESS("Capabilities et rôles système synchronisés."))
