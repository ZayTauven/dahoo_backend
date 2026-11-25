import re
from datetime import date

from django.http import HttpResponse
from django.utils import timezone
from rest_framework.exceptions import ValidationError

MONTH = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


def parse_month(value):
    """« 2026-11 » → 1er novembre 2026 ; le mois courant si absent."""
    if not value:
        return timezone.localdate().replace(day=1)
    match = MONTH.match(value)
    if not match or not 2000 <= int(match[1]) <= 2100:
        raise ValidationError({"month": "Mois attendu au format AAAA-MM."})
    return date(int(match[1]), int(match[2]), 1)


def pdf_response(document):
    response = HttpResponse(document.content, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{document.filename}"'
    # Données personnelles : jamais dans un cache partagé ni indexées.
    response["Cache-Control"] = "private, no-store"
    response["X-Robots-Tag"] = "noindex"
    return response
