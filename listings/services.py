from rest_framework.exceptions import ValidationError

from listings.models import Listing


def check_publishable(listing):
    """Une annonce publiée porte sur un lot disponible, et une seule annonce par type l'est à la fois."""
    unit = listing.unit
    if unit.status == "SOLD":
        raise ValidationError({"unit": "Ce lot est vendu."})
    if listing.listing_type == "RENT" and unit.status == "RENTED":
        raise ValidationError({"unit": "Ce lot est déjà loué."})
    others = Listing.objects.filter(unit=unit, listing_type=listing.listing_type, status="PUBLISHED")
    if others.exclude(pk=listing.pk).exists():
        raise ValidationError({"unit": "Une autre annonce de ce lot est déjà publiée."})
