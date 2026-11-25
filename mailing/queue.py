"""File d'envoi : enregistrer un message, l'envoyer aussitôt en arrière-plan, réessayer plus tard s'il échoue."""

import logging
import threading

from django.conf import settings
from django.core.mail import get_connection
from django.db import IntegrityError, close_old_connections, transaction
from django.utils import timezone

from mailing.addresses import is_deliverable
from mailing.catalog import CATALOG
from mailing.models import EmailOptOut, OutgoingEmail
from mailing.render import build_message

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5


def queue_email(template, to, context, *, organization=None, dedupe_key=""):
    """
    Met un e-mail en file et lance son envoi une fois la transaction validée. Renvoie None si l'adresse
    est vide ou fictive, si la personne s'est désinscrite, ou si ce rappel est déjà parti.
    """
    spec = CATALOG[template]
    to = (to or "").strip()
    if not is_deliverable(to):
        return None
    if spec.reminder and organization and EmailOptOut.objects.filter(organization=organization, email=to.lower()).exists():
        return None
    try:
        with transaction.atomic():
            email = OutgoingEmail.objects.create(
                organization=organization, to=to, template=template, dedupe_key=dedupe_key,
                context={key: "" if value is None else value for key, value in context.items()},
            )
    except IntegrityError:
        return None  # Même clé : déjà en file ou déjà envoyé.
    transaction.on_commit(lambda: _deliver_soon(email.pk))
    return email


def _deliver_soon(pk):
    if not settings.EMAIL_SEND_IN_BACKGROUND:
        deliver([pk])
        return

    def run():
        try:
            deliver([pk])
        except Exception:  # noqa: BLE001 - la commande `send_emails` réessaiera
            logger.exception("Envoi de l'e-mail %s impossible", pk)
        finally:
            close_old_connections()

    threading.Thread(target=run, daemon=True).start()


def deliver(ids=None, limit=200):
    """Envoie les messages en attente (ou ceux donnés). Renvoie (envoyés, échecs)."""
    sent = failed = 0
    pending = OutgoingEmail.objects.filter(status="PENDING", attempts__lt=MAX_ATTEMPTS)
    if ids is not None:
        pending = pending.filter(pk__in=ids)
    connection = None
    for pk in list(pending.order_by("created_at").values_list("pk", flat=True)[:limit]):
        with transaction.atomic():
            # Verrou : l'envoi immédiat et la tâche planifiée ne prennent pas le même message.
            email = (
                OutgoingEmail.objects.select_for_update(skip_locked=True, of=("self",))
                .select_related("organization").filter(pk=pk, status="PENDING").first()
            )
            if email is None:
                continue
            if not settings.EMAIL_ENABLED:
                email.status, email.error = "SKIPPED", "Envois désactivés (EMAIL_ENABLED)."
                email.save(update_fields=["status", "error"])
                continue
            email.attempts += 1
            try:
                connection = connection or get_connection()
                build_message(email, connection).send()
            except Exception as error:  # noqa: BLE001 - SMTP, réseau, gabarit : journalisé, jamais propagé
                logger.warning("E-mail %s (%s) non envoyé : %s", email.pk, email.template, error)
                email.error = f"{type(error).__name__}: {error}"[:300]
                email.status = "FAILED" if email.attempts >= MAX_ATTEMPTS else "PENDING"
                connection = None
                failed += 1
            else:
                email.status, email.error, email.sent_at = "SENT", "", timezone.now()
                sent += 1
            email.save(update_fields=["status", "attempts", "error", "sent_at"])
    return sent, failed
