from django.core.management.base import BaseCommand

from mailing.queue import deliver


class Command(BaseCommand):
    help = "Envoie les e-mails en attente (réessais compris) : à planifier toutes les cinq minutes."

    def handle(self, *args, **options):
        sent, failed = deliver()
        self.stdout.write(f"{sent} e-mail(s) envoyé(s), {failed} échec(s).")
