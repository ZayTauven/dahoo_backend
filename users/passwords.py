"""
Mots de passe. Les comptes s'identifient par téléphone et Dahoo n'envoie pas encore de SMS : un mot de
passe oublié se réinitialise auprès de l'administrateur de son agence, ou de l'équipe Dahoo.
"""

import secrets

from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

# Sans caractères ambigus à dicter (0/O, 1/l/I).
ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
TEMPORARY_LENGTH = 10


def close_sessions(user):
    """Déconnecte l'utilisateur partout : ses jetons de renouvellement ne servent plus."""
    for token in OutstandingToken.objects.filter(user=user, blacklistedtoken__isnull=True):
        BlacklistedToken.objects.get_or_create(token=token)


def change_password(user, password):
    user.set_password(password)
    user.save(update_fields=["password"])
    close_sessions(user)


def reset_password(user):
    """Mot de passe provisoire, renvoyé une seule fois à la personne qui réinitialise."""
    password = "".join(secrets.choice(ALPHABET) for _ in range(TEMPORARY_LENGTH))
    change_password(user, password)
    return password


def ensure_agency_can_reset(organization, user):
    """
    Une agence ne réinitialise que les comptes qu'elle est seule à employer : sinon son administrateur
    pourrait entrer dans une autre agence, ou dans la plateforme, avec le compte d'un membre commun.
    """
    elsewhere = user.memberships.exclude(organization=organization).exists()
    if user.is_staff or user.is_superuser or elsewhere:
        raise PermissionDenied("Ce compte est utilisé ailleurs que dans votre agence : contactez l'équipe Dahoo.")
