from decimal import Decimal

from django.utils import timezone
from rest_framework.exceptions import ValidationError

from analytics.dashboard import schedules_with_remaining
from dahoo.whatsapp import whatsapp_url
from leases.tenants import tenant_names
from notifications.services import money
from payments.models import RentReminder


def reminder_for(lease, *, today=None):
    """Relance prête à envoyer : montant dû, message et lien WhatsApp. Rien n'est enregistré."""
    today = today or timezone.localdate()
    due = list(
        schedules_with_remaining(lease.organization)
        .filter(lease_contract=lease, is_paid=False, remaining__gt=0, due_date__lte=today)
        .order_by("due_date")
    )
    if not due:
        raise ValidationError({"detail": "Ce locataire n'a aucun loyer en retard."})
    total = sum((schedule.remaining for schedule in due), Decimal("0"))
    first_name = tenant_names(lease.organization)(lease.tenant)
    since = f"depuis le {due[0].due_date:%d/%m/%Y}"
    what = f"un loyer {since}" if len(due) == 1 else f"{len(due)} échéances, la plus ancienne {since}"
    message = (
        f"Bonjour {first_name}, sauf erreur de notre part, il reste {money(total)} à régler pour le logement "
        f"{lease.unit.reference} ({lease.unit.building.property.name}) : {what}. "
        f"Merci de nous indiquer quand vous pourrez régulariser. {lease.organization.name}"
    ).replace("\u00a0", " ").replace("\u202f", " ")
    return {
        "amount": total,
        "count": len(due),
        "since": due[0].due_date,
        "message": message,
        "whatsapp_url": whatsapp_url(lease.tenant.phone, message),
    }


def record_reminder(lease, *, user, channel):
    """Trace la relance (envoyée par l'agence depuis son téléphone) et renvoie le message à envoyer."""
    reminder = reminder_for(lease)
    RentReminder.objects.create(
        organization_id=lease.organization_id, lease=lease, channel=channel,
        amount=reminder["amount"], message=reminder["message"], sent_by=user,
    )
    return reminder
