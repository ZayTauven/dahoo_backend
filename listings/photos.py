from django.db.models import Count, OuterRef, Subquery

from listings.models import ListingPhoto

MAX_PHOTO_SIZE = 8 * 1024 * 1024  # 8 Mo
MAX_PHOTOS_PER_LISTING = 20
# Formats Pillow acceptés (détectés sur le contenu du fichier, pas sur son extension).
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


def with_cover(queryset, count=False):
    """Annote `cover_image` (fichier de la 1re photo) et, si demandé, `photos_count`."""
    first_photo = ListingPhoto.objects.filter(listing=OuterRef("pk")).order_by("position", "id")
    queryset = queryset.annotate(cover_image=Subquery(first_photo.values("image")[:1]))
    if count:
        queryset = queryset.annotate(photos_count=Count("photos", distinct=True))
    return queryset


def media_url(request, name):
    """URL absolue d'un fichier stocké (None si pas de fichier)."""
    if not name:
        return None
    url = ListingPhoto._meta.get_field("image").storage.url(name)
    return request.build_absolute_uri(url) if request is not None else url


def cover_url(request, listing):
    """Couverture d'une annonce : annotation `cover_image` si présente, sinon lecture en base."""
    if hasattr(listing, "cover_image"):
        name = listing.cover_image
    else:
        name = listing.photos.values_list("image", flat=True).first()
    return media_url(request, name)
