from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from mailing.catalog import CATALOG
from mailing.models import OutgoingEmail
from mailing.queue import deliver
from mailing.samples import SAMPLES
from organizations.models import Organization


class Command(BaseCommand):
    help = "Envoie un exemplaire de chaque e-mail (ou d'un seul) à une adresse, avec des données fictives."

    def add_arguments(self, parser):
        parser.add_argument("to", help="Adresse qui reçoit les exemplaires.")
        parser.add_argument("--template", choices=sorted(CATALOG), help="Un seul gabarit.")

    def handle(self, to, template=None, **options):
        if "smtp" in settings.EMAIL_BACKEND and not settings.EMAIL_HOST_PASSWORD:
            raise CommandError("EMAIL_HOST_USER et EMAIL_HOST_PASSWORD sont vides dans .env.")
        organization = Organization.objects.filter(kind="AGENCY").order_by("id").first()
        emails = [
            OutgoingEmail.objects.create(
                to=to, template=code, context=SAMPLES[code], organization=organization if CATALOG[code].on_behalf else None
            )
            for code in ([template] if template else CATALOG)
        ]
        sent, failed = deliver([email.pk for email in emails])
        for email in OutgoingEmail.objects.filter(pk__in=[email.pk for email in emails]).exclude(status="SENT"):
            self.stderr.write(f"{email.template} : {email.error or email.status}")
        self.stdout.write(self.style.SUCCESS(f"{sent} e-mail(s) envoyé(s) à {to}, {failed} échec(s)."))
