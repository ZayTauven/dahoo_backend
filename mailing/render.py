"""Fabrication d'un message : HTML, repli texte, illustrations embarquées, en-têtes d'expédition."""

import re
from email.message import MIMEPart
from email.utils import formataddr, parseaddr
from functools import lru_cache
from html import unescape
from pathlib import Path

from django.conf import settings
from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from documents.pdf import phone
from mailing.addresses import is_deliverable
from mailing.catalog import CATALOG

ILLUSTRATIONS = Path(__file__).resolve().parent / "illustrations"
OPT_OUT_SALT = "dahoo.email-opt-out"

_INERT = re.compile(r"<(script|style|head)\b.*?</\1>", re.S | re.I)
_COMMENTS = re.compile(r"<!--.*?-->", re.S)
_PREHEADER = re.compile(r"<span[^>]*display:none.*?</span>", re.S | re.I)
_LINK = re.compile(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S | re.I)
_BLOCK_END = re.compile(r"</(?:p|tr|div|h[1-6])>|<br\s*/?>", re.I)
_TAGS = re.compile(r"<[^>]+>")


def plain_text(html):
    """Repli texte : mêmes mots, liens en clair."""
    text = _PREHEADER.sub("", _COMMENTS.sub("", _INERT.sub("", html)))
    text = _LINK.sub(lambda match: f"{match[2]} : {match[1]}", text)
    text = unescape(_TAGS.sub("", _BLOCK_END.sub("\n", text)))
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"


class _Missing(dict):
    def __missing__(self, key):
        return ""


def opt_out_token(organization_id, email):
    return signing.dumps({"o": organization_id, "e": email.lower()}, salt=OPT_OUT_SALT)


@lru_cache(maxsize=None)
def _image(name):
    return (ILLUSTRATIONS / f"{name}.png").read_bytes()


def _attach(message, name, cid):
    # Image embarquée (cid:) : elle s'affiche sans serveur public, y compris en développement.
    part = MIMEPart()
    part.set_content(_image(name), maintype="image", subtype="png", disposition="inline", filename=f"{cid}.png", cid=f"<{cid}>")
    message.attach(part)


def build_message(email, connection=None):
    spec = CATALOG[email.template]
    organization = email.organization
    opt_out = ""
    if spec.reminder and organization is not None:
        opt_out = f"{settings.PUBLIC_SITE_URL}/desinscription/{opt_out_token(organization.pk, email.to)}"
    html = render_to_string(f"emails/{email.template}.html", {
        **email.context,
        "label": spec.label,
        "organization_name": organization.name if organization and spec.on_behalf else "",
        "organization_phone": phone(organization.phone) if organization and spec.on_behalf else "",
        "can_reply": bool(organization and spec.on_behalf and is_deliverable(organization.email)),
        "site_url": settings.PUBLIC_SITE_URL,
        "opt_out_url": opt_out,
        "year": timezone.localdate().year,
    })
    # Un objet tient sur une ligne : les retours saisis dans un nom sont retirés.
    subject = " ".join(spec.subject.format_map(_Missing(email.context)).split())
    sender, reply_to = settings.DEFAULT_FROM_EMAIL, []
    if spec.on_behalf and organization is not None:
        name = " ".join(organization.name.split())
        sender = formataddr((f"{name} via Dahoo", parseaddr(settings.DEFAULT_FROM_EMAIL)[1]))
        reply_to = [organization.email] if is_deliverable(organization.email) else []
    elif settings.EMAIL_REPLY_TO:
        reply_to = [settings.EMAIL_REPLY_TO]

    recipient = email.to
    if settings.EMAIL_TEST_RECIPIENT:
        # Recette : tout part vers une seule boîte, le vrai destinataire est rappelé dans l'objet.
        recipient, subject = settings.EMAIL_TEST_RECIPIENT, f"[{email.to}] {subject}"
    message = EmailMultiAlternatives(subject, plain_text(html), sender, [recipient], reply_to=reply_to, connection=connection)
    if opt_out:
        message.extra_headers["List-Unsubscribe"] = f"<{opt_out}>"
    message.attach_alternative(html, "text/html")
    _attach(message, spec.illustration, "illustration")
    _attach(message, "logo", "logo")
    return message
