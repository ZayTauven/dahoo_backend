"""Photos d'état des lieux : réduites à l'envoi, privées, lues par un lien signé valable jusqu'au lendemain."""

from datetime import date, timedelta
from io import BytesIO

from django.core import signing
from django.core.files.base import ContentFile
from django.utils import timezone
from PIL import Image, ImageOps
from rest_framework import serializers

MAX_PHOTO_SIZE = 12 * 1024 * 1024
MAX_PHOTOS = 80
MAX_SIDE = 1600
FORMATS = {"JPEG", "PNG", "WEBP"}
SALT = "dahoo.inspection-photo"


def prepare(upload):
    """JPEG de 1600 px au plus, redressé, sans métadonnées (la position GPS d'un téléphone n'a rien à faire ici)."""
    if upload.size > MAX_PHOTO_SIZE:
        raise serializers.ValidationError("Image trop volumineuse (12 Mo maximum).")
    try:
        upload.seek(0)
        image = Image.open(upload)
        if image.format not in FORMATS:
            raise serializers.ValidationError("Format non accepté : JPEG, PNG ou WebP uniquement.")
        image = ImageOps.exif_transpose(image).convert("RGB")
    except serializers.ValidationError:
        raise
    except Exception:  # noqa: BLE001 - fichier tronqué ou image piégée
        raise serializers.ValidationError("Cette image est illisible.")
    image.thumbnail((MAX_SIDE, MAX_SIDE))
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=82, optimize=True)
    return ContentFile(buffer.getvalue(), name="photo.jpg")


def photo_path(photo):
    """Chemin d'API signé, stable dans la journée (l'image reste en cache)."""
    token = signing.Signer(salt=SALT).sign_object({"p": photo.pk, "d": timezone.localdate().isoformat()})
    return f"/api/v1/inspections/photos/file/{token}/"


def photo_id(token):
    """Identifiant de la photo, ou None si le lien est faux ou périmé."""
    try:
        data = signing.Signer(salt=SALT).unsign_object(token)
        issued = date.fromisoformat(data["d"])
    except (signing.BadSignature, KeyError, ValueError, TypeError):
        return None
    return data["p"] if timezone.localdate() - issued <= timedelta(days=1) else None
