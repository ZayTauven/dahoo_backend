from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers

from organizations.models import Membership

User = get_user_model()


def validate_new_member(organization, attrs):
    """
    Vérifie qu'un membre peut être ajouté par téléphone. Si aucun compte n'existe,
    prénom, nom et mot de passe sont requis pour le créer. Renvoie le compte existant ou None.
    """
    user = User.objects.filter(phone=attrs["phone"]).first()
    if user and organization is not None and Membership.objects.filter(user=user, organization=organization).exists():
        raise serializers.ValidationError({"phone": "Cet utilisateur est déjà membre de l'organisation."})
    if user is None:
        missing = [field for field in ("first_name", "last_name", "password") if not attrs.get(field)]
        if missing:
            raise serializers.ValidationError({field: "Obligatoire pour créer un nouveau compte." for field in missing})
        validate_password(attrs["password"])
    return user


@transaction.atomic
def add_member(organization, role, *, phone, existing_user=None, first_name=None, last_name=None, email=None, password=None):
    user = existing_user
    if user is None:
        user = User.objects.create_user(
            phone=phone, password=password, first_name=first_name, last_name=last_name, email=email or None
        )
    return Membership.objects.create(user=user, organization=organization, role=role)
