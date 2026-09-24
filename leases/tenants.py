from django.contrib.auth import get_user_model
from django.db import transaction

from leases.models import Tenant

User = get_user_model()


@transaction.atomic
def register_tenant(organization, *, phone, first_name, last_name, **profile):
    """
    Enregistre un locataire dans l'organisation. Le compte est retrouvé par téléphone ou créé
    sans mot de passe utilisable (le locataire ne se connecte pas encore).
    """
    user = User.objects.filter(phone=phone).first()
    if user is None:
        user = User(phone=phone, first_name=first_name, last_name=last_name, email=profile.get("email") or None)
        user.set_unusable_password()
        user.save()
    return Tenant.objects.create(
        organization=organization, user=user, first_name=first_name, last_name=last_name, **profile
    )
