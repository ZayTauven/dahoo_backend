import itertools
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from access.models import Role
from leases.models import LeaseContract
from leases.tenants import register_tenant
from organizations.models import Membership, Organization
from payments.models import PaymentMethod, PaymentSchedule
from properties.models import Building, Property, Unit

User = get_user_model()
PASSWORD = "Motdepasse!2026"
_sequence = itertools.count(1)


def make_user(**fields):
    n = next(_sequence)
    data = {"phone": f"+22170{n:07d}", "first_name": "Awa", "last_name": f"Diop{n}"}
    data.update(fields)
    return User.objects.create_user(password=PASSWORD, **data)


def make_org(name="Agence"):
    return Organization.objects.create(name=name)


def add_member(organization, user=None, role="ORG_ADMIN"):
    user = user or make_user()
    Membership.objects.create(user=user, organization=organization, role=Role.objects.get(code=role))
    return user


def client_for(user, organization=None):
    client = APIClient()
    client.force_authenticate(user)
    if organization is not None:
        client.credentials(HTTP_X_ORGANIZATION_ID=str(organization.id))
    return client


def make_unit(organization, status="FREE"):
    prop = Property.objects.create(organization=organization, name="Résidence", address="Rue 1", city="Dakar")
    building = Building.objects.create(property=prop, name="Bâtiment A")
    return Unit.objects.create(building=building, reference=f"A{next(_sequence)}", unit_type="T2", surface=60, status=status)


def make_tenant(organization, phone=None, first_name="Ibrahima", last_name="Sarr"):
    """Enregistre un locataire dans l'organisation et renvoie son compte (id attendu par l'API)."""
    phone = phone or f"+22176{next(_sequence):07d}"
    return register_tenant(organization, phone=phone, first_name=first_name, last_name=last_name).user


def make_lease(organization, unit=None, tenant=None, created_by=None, status="DRAFT"):
    unit = unit or make_unit(organization)
    return LeaseContract.objects.create(
        organization=organization,
        unit=unit,
        tenant=tenant or make_user(),
        created_by=created_by or make_user(),
        start_date="2026-01-01",
        rent_amount=Decimal("150000"),
        status=status,
    )


def make_schedule(lease, amount="150000"):
    return PaymentSchedule.objects.create(
        organization=lease.organization,
        lease_contract=lease,
        schedule_type="RENT",
        due_date="2026-02-01",
        amount_due=Decimal(amount),
    )


def payment_method():
    method, _ = PaymentMethod.objects.get_or_create(code="WAVE", defaults={"label": "Wave"})
    return method


def results(response):
    """Contenu d'une liste, paginée ou non."""
    data = response.json()
    return data["results"] if isinstance(data, dict) and "results" in data else data


# Hachage rapide : les tests créent beaucoup de comptes, PBKDF2 les ralentirait fortement.
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DahooTestCase(APITestCase):
    """Deux organisations étanches : A (admin_a) et B (admin_b)."""

    def setUp(self):
        cache.clear()  # remet à zéro les compteurs de throttling entre les tests
        self.org_a = make_org("Agence A")
        self.org_b = make_org("Agence B")
        self.admin_a = add_member(self.org_a)
        self.admin_b = add_member(self.org_b)
        self.api_a = client_for(self.admin_a)
        self.api_b = client_for(self.admin_b)
