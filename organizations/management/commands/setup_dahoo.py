from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from access.models import Role
from organizations.models import Membership, Organization

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Fait d'un compte existant un administrateur de la plateforme Dahoo (staff) et l'inscrit comme "
        "administrateur de l'organisation interne Dahoo, créée si besoin. Idempotent."
    )

    def add_arguments(self, parser):
        parser.add_argument("phone", help="Téléphone du compte à promouvoir")
        parser.add_argument("--name", default="Dahoo", help="Nom de l'organisation interne (défaut : Dahoo)")

    @transaction.atomic
    def handle(self, phone, name, **options):
        user = User.objects.filter(phone=phone).first()
        if user is None:
            raise CommandError(f"Aucun compte avec le téléphone {phone} (créez-le avec createsuperuser).")

        if not user.is_staff:
            user.is_staff = True
            user.save(update_fields=["is_staff"])

        organization = Organization.objects.filter(is_internal=True).order_by("id").first()
        if organization is None:
            organization = Organization.objects.create(name=name, is_internal=True)

        admin_role = Role.objects.get(code="ORG_ADMIN")
        membership, created = Membership.objects.get_or_create(
            user=user, organization=organization, defaults={"role": admin_role}
        )
        if not created and (membership.role_id != admin_role.id or not membership.is_active):
            membership.role = admin_role
            membership.is_active = True
            membership.save(update_fields=["role", "is_active"])

        self.stdout.write(self.style.SUCCESS(
            f"{user.first_name} est administrateur de la plateforme et de l'organisation « {organization.name} »."
        ))
