from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from access.models import Capability
from organizations.models import Membership, Organization
from subscriptions.models import SubscriptionPlan

from .factories import PASSWORD, DahooTestCase, add_member, client_for, make_user

PLATFORM = "/api/v1/platform/organizations/"
NEW_AGENCY = {
    "name": "Agence Teranga",
    "city": "Dakar",
    "admin": {"phone": "+221775556677", "first_name": "Ousmane", "last_name": "Diallo", "password": "Teranga!2026"},
}


class PlatformTests(DahooTestCase):
    def setUp(self):
        super().setUp()
        self.dahoo_admin = make_user(is_staff=True)
        self.platform = client_for(self.dahoo_admin)

    def create_agency(self, payload=NEW_AGENCY):
        return self.platform.post(PLATFORM, payload, format="json")

    def test_reserved_to_dahoo_team(self):
        self.assertEqual(self.api_a.get(PLATFORM).status_code, 403)
        self.assertEqual(self.api_a.post(PLATFORM, NEW_AGENCY, format="json").status_code, 403)
        self.assertEqual(APIClient().get(PLATFORM).status_code, 401)

    def test_full_flow_new_agency_admin_can_work(self):
        response = self.create_agency()
        self.assertEqual(response.status_code, 201, response.content)
        agency = response.json()
        self.assertEqual(agency["access_status"], "TRIAL")
        self.assertEqual(agency["member_count"], 1)

        # L'administrateur de l'agence se connecte et travaille dans son agence.
        login = APIClient().post("/api/v1/users/login/", {"phone": "+221775556677", "password": "Teranga!2026"})
        self.assertEqual(login.status_code, 200)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['access']}")
        me = client.get("/api/v1/users/me/").json()
        self.assertFalse(me["is_platform_admin"])
        self.assertEqual(me["memberships"][0]["role"], "ORG_ADMIN")
        response = client.post("/api/v1/properties/properties/", {"name": "Résidence", "address": "a", "city": "Dakar"})
        self.assertEqual(response.status_code, 201)

    def test_existing_account_can_become_agency_admin(self):
        payload = {**NEW_AGENCY, "admin": {"phone": self.admin_b.phone}}
        self.assertEqual(self.create_agency(payload).status_code, 201)
        self.admin_b.refresh_from_db()
        self.assertTrue(self.admin_b.check_password(PASSWORD))
        self.assertEqual(self.admin_b.memberships.count(), 2)

    def test_incomplete_admin_creates_nothing(self):
        payload = {**NEW_AGENCY, "admin": {"phone": "+221770000099"}}
        self.assertEqual(self.create_agency(payload).status_code, 400)
        self.assertFalse(Organization.objects.filter(name="Agence Teranga").exists())

    def test_extend_trial(self):
        self.org_a.trial_ends_at = timezone.now() - timedelta(days=1)
        self.org_a.save()
        self.assertEqual(self.api_a.post("/api/v1/leases/tenants/", {"phone": "+221771234000", "first_name": "a", "last_name": "b"}).status_code, 402)
        new_end = (timezone.now() + timedelta(days=15)).isoformat()
        response = self.platform.patch(f"{PLATFORM}{self.org_a.id}/", {"trial_ends_at": new_end})
        self.assertEqual(response.json()["access_status"], "TRIAL")
        self.assertEqual(self.api_a.post("/api/v1/leases/tenants/", {"phone": "+221771234000", "first_name": "a", "last_name": "b"}).status_code, 201)

    def test_suspend_agency(self):
        self.platform.patch(f"{PLATFORM}{self.org_a.id}/", {"is_active": False})
        self.assertEqual(self.api_a.get("/api/v1/properties/properties/").status_code, 403)
        self.assertEqual(self.api_b.get("/api/v1/properties/properties/").status_code, 200)

    def test_assign_then_suspend_subscription(self):
        self.org_a.trial_ends_at = timezone.now() - timedelta(days=1)
        self.org_a.save()
        plan = SubscriptionPlan.objects.create(name="Pro", billing_type="MONTHLY", price=50000)
        response = self.platform.post(
            f"{PLATFORM}{self.org_a.id}/subscriptions/", {"plan": plan.id, "start_date": timezone.localdate().isoformat()}
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(self.platform.get(f"{PLATFORM}{self.org_a.id}/").json()["access_status"], "ACTIVE")

        self.platform.patch(f"/api/v1/platform/subscriptions/{response.json()['id']}/", {"status": "SUSPENDED"})
        self.assertEqual(self.platform.get(f"{PLATFORM}{self.org_a.id}/").json()["access_status"], "EXPIRED")

    def test_list_search_and_members(self):
        names = [org["name"] for org in self.platform.get(f"{PLATFORM}?search=agence a").json()["results"]]
        self.assertEqual(names, ["Agence A"])
        members = self.platform.get(f"{PLATFORM}{self.org_a.id}/members/").json()["results"]
        self.assertEqual(members[0]["user"]["id"], self.admin_a.id)

    def test_me_flags_platform_admin(self):
        self.assertTrue(self.platform.get("/api/v1/users/me/").json()["is_platform_admin"])


class DahooOrganizationTests(DahooTestCase):
    def test_setup_command_is_idempotent(self):
        user = make_user()
        for _ in range(2):
            call_command("setup_dahoo", user.phone, stdout=StringIO())
        user.refresh_from_db()
        self.assertTrue(user.is_staff)
        dahoo = Organization.objects.get(is_internal=True)
        self.assertEqual(Membership.objects.get(user=user, organization=dahoo).role.code, "ORG_ADMIN")

    def test_internal_organization_never_expires(self):
        dahoo = Organization.objects.create(name="Dahoo", is_internal=True, trial_ends_at=timezone.now() - timedelta(days=365))
        client = client_for(add_member(dahoo))
        self.assertEqual(client.get("/api/v1/organizations/current/").json()["access_status"], "ACTIVE")
        response = client.post("/api/v1/properties/properties/", {"name": "Siège", "address": "a", "city": "Dakar"})
        self.assertEqual(response.status_code, 201)

    def test_every_capability_has_a_label(self):
        self.assertFalse(Capability.objects.filter(description="").exists())
