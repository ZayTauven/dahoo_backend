from django.contrib.auth import get_user_model

from leases.models import Tenant

from .factories import PASSWORD, DahooTestCase, add_member, client_for, make_lease, make_tenant, results

User = get_user_model()
TENANTS_URL = "/api/v1/leases/tenants/"
NEW_TENANT = {"phone": "+221 77 111 22 33", "first_name": "Aminata", "last_name": "Ba", "email": "aminata@example.com"}


class TenantTests(DahooTestCase):
    def test_create_tenant_then_lease(self):
        response = self.api_a.post(TENANTS_URL, NEW_TENANT)
        self.assertEqual(response.status_code, 201, response.content)
        tenant = response.json()
        self.assertEqual(tenant["phone"], "+221771112233")  # espaces retirés
        self.assertEqual(tenant["active_leases"], 0)

        lease = make_lease(self.org_a)
        response = self.api_a.post(
            "/api/v1/leases/",
            {"unit": lease.unit.id, "tenant": tenant["id"], "start_date": "2026-01-01", "rent_amount": "150000"},
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["tenant"], tenant["id"])

    def test_tenant_account_cannot_log_in(self):
        tenant_id = self.api_a.post(TENANTS_URL, NEW_TENANT).json()["id"]
        self.assertFalse(User.objects.get(pk=tenant_id).has_usable_password())
        response = self.client.post("/api/v1/users/login/", {"phone": "+221771112233", "password": ""})
        self.assertEqual(response.status_code, 400)

    def test_duplicate_phone_in_same_organization(self):
        self.api_a.post(TENANTS_URL, NEW_TENANT)
        response = self.api_a.post(TENANTS_URL, NEW_TENANT)
        self.assertEqual(response.status_code, 400)
        self.assertIn("phone", response.json())

    def test_same_person_in_two_agencies_keeps_separate_records(self):
        first = self.api_a.post(TENANTS_URL, NEW_TENANT).json()
        second = self.api_b.post(TENANTS_URL, {**NEW_TENANT, "first_name": "Amina", "email": ""}).json()
        # Même compte (même téléphone) : les baux et paiements pointent vers la même personne...
        self.assertEqual(first["id"], second["id"])
        # ...mais chaque agence ne voit que sa propre fiche.
        self.assertEqual(self.api_b.get(f"{TENANTS_URL}{second['id']}/").json()["first_name"], "Amina")
        self.assertEqual(self.api_a.get(f"{TENANTS_URL}{first['id']}/").json()["first_name"], "Aminata")
        self.assertEqual(self.api_b.get(f"{TENANTS_URL}{second['id']}/").json()["email"], "")

    def test_existing_member_account_is_reused_without_changing_it(self):
        member = add_member(self.org_b)
        response = self.api_a.post(TENANTS_URL, {"phone": member.phone, "first_name": "Autre", "last_name": "Nom"})
        self.assertEqual(response.status_code, 201)
        member.refresh_from_db()
        self.assertNotEqual(member.first_name, "Autre")
        self.assertTrue(member.check_password(PASSWORD))

    def test_tenants_are_isolated(self):
        tenant = make_tenant(self.org_a)
        self.assertEqual(results(self.api_b.get(TENANTS_URL)), [])
        self.assertEqual(self.api_b.get(f"{TENANTS_URL}{tenant.id}/").status_code, 404)
        self.assertEqual(self.api_b.patch(f"{TENANTS_URL}{tenant.id}/", {"notes": "x"}).status_code, 404)

    def test_phone_cannot_be_changed(self):
        tenant = make_tenant(self.org_a)
        response = self.api_a.patch(f"{TENANTS_URL}{tenant.id}/", {"phone": "+221700000000"})
        self.assertEqual(response.status_code, 400)
        response = self.api_a.patch(f"{TENANTS_URL}{tenant.id}/", {"notes": "Paie toujours en avance"})
        self.assertEqual(response.status_code, 200)

    def test_active_lease_count(self):
        tenant = make_tenant(self.org_a)
        make_lease(self.org_a, tenant=tenant, status="ACTIVE")
        make_lease(self.org_a, tenant=tenant, status="COMPLETED")
        make_lease(self.org_b, tenant=tenant, status="ACTIVE")  # autre agence : non compté
        self.assertEqual(self.api_a.get(f"{TENANTS_URL}{tenant.id}/").json()["active_leases"], 1)

    def test_tenant_with_leases_cannot_be_deleted(self):
        tenant = make_tenant(self.org_a)
        make_lease(self.org_a, tenant=tenant)
        self.assertEqual(self.api_a.delete(f"{TENANTS_URL}{tenant.id}/").status_code, 400)
        other = make_tenant(self.org_a)
        self.assertEqual(self.api_a.delete(f"{TENANTS_URL}{other.id}/").status_code, 204)
        self.assertFalse(Tenant.objects.filter(user=other).exists())

    def test_viewer_cannot_create_tenant(self):
        viewer = client_for(add_member(self.org_a, role="VIEWER"))
        self.assertEqual(viewer.get(TENANTS_URL).status_code, 200)
        self.assertEqual(viewer.post(TENANTS_URL, NEW_TENANT).status_code, 403)
