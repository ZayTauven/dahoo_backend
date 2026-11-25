from django.contrib.auth import get_user_model
from django.db import transaction

from owners.models import Owner

User = get_user_model()


@transaction.atomic
def register_owner(organization, *, phone, first_name, last_name, **profile):
    """Enregistre un bailleur ; le compte est retrouvé par téléphone ou créé sans mot de passe utilisable."""
    user = User.objects.filter(phone=phone).first()
    if user is None:
        user = User(phone=phone, first_name=first_name, last_name=last_name, email=profile.get("email") or None)
        user.set_unusable_password()
        user.save()
    return Owner.objects.create(
        organization=organization, user=user, first_name=first_name, last_name=last_name, **profile
    )
