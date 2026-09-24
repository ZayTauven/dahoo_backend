from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import CharField, OuterRef, Subquery, Value
from django.db.models.functions import Concat

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


def tenant_name_subquery(user_ref, organization_ref="organization"):
    """
    Sous-requête : nom de la personne tel que l'organisation l'a saisi dans sa fiche locataire
    (NULL si la personne n'a pas de fiche, ex. un acquéreur). À combiner avec `person_name`.
    """
    profiles = Tenant.objects.filter(organization=OuterRef(organization_ref), user=OuterRef(user_ref))
    full_name = Concat("first_name", Value(" "), "last_name", output_field=CharField())
    return Subquery(profiles.annotate(full_name=full_name).values("full_name")[:1])


def person_name(obj, annotation, user, organization_id):
    """
    Nom affiché : annotation `annotation` (voir tenant_name_subquery) si présente, sinon lecture
    de la fiche locataire ; à défaut, nom du compte.
    """
    if hasattr(obj, annotation):
        name = getattr(obj, annotation)
    else:
        name = (
            Tenant.objects.filter(organization_id=organization_id, user=user)
            .values_list("first_name", "last_name")
            .first()
        )
        name = " ".join(name) if name else None
    return name or f"{user.first_name} {user.last_name}".strip()
