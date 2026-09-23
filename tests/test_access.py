from django.urls import URLPattern, URLResolver, get_resolver

from access.catalog import CAPABILITIES, SYSTEM_ROLES
from access.models import Role
from access.permissions import METHOD_ACTIONS, HasCapability, get_required_capability

from .factories import DahooTestCase, add_member, client_for, make_user


def iter_views(patterns=None):
    for pattern in patterns if patterns is not None else get_resolver().url_patterns:
        if isinstance(pattern, URLResolver):
            yield from iter_views(pattern.url_patterns)
        elif isinstance(pattern, URLPattern) and hasattr(pattern.callback, "view_class"):
            yield pattern.callback.view_class


class CatalogTests(DahooTestCase):
    def test_system_roles_are_synced(self):
        for code, spec in SYSTEM_ROLES.items():
            role = Role.objects.get(code=code)
            self.assertEqual(set(role.capabilities.values_list("code", flat=True)), spec["capabilities"])

    def test_viewer_role_is_read_only(self):
        self.assertTrue(all(code.endswith(".view") for code in SYSTEM_ROLES["VIEWER"]["capabilities"]))

    def test_every_view_capability_exists_in_catalog(self):
        missing = set()
        for view_class in iter_views():
            if HasCapability not in getattr(view_class, "permission_classes", []):
                continue
            view = view_class()
            for method in METHOD_ACTIONS:
                if method.lower() not in view_class.http_method_names or not hasattr(view_class, method.lower()):
                    continue
                required = get_required_capability(view, method)
                if required and required not in CAPABILITIES:
                    missing.add(f"{view_class.__name__} {method}: {required}")
        self.assertEqual(missing, set())


class OrganizationContextTests(DahooTestCase):
    def test_user_without_organization_is_forbidden(self):
        response = client_for(make_user()).get("/api/v1/properties/properties/")
        self.assertEqual(response.status_code, 403)

    def test_multi_organization_user_must_choose(self):
        add_member(self.org_b, user=self.admin_a, role="VIEWER")
        self.assertEqual(self.api_a.get("/api/v1/properties/properties/").status_code, 400)
        response = client_for(self.admin_a, self.org_b).get("/api/v1/properties/properties/")
        self.assertEqual(response.status_code, 200)

    def test_cannot_target_foreign_organization(self):
        response = client_for(self.admin_a, self.org_b).get("/api/v1/properties/properties/")
        self.assertEqual(response.status_code, 403)

    def test_inactive_membership_loses_access(self):
        self.admin_a.memberships.update(is_active=False)
        self.assertEqual(self.api_a.get("/api/v1/properties/properties/").status_code, 403)

    def test_superuser_can_target_any_organization(self):
        superuser = make_user(is_superuser=True, is_staff=True)
        response = client_for(superuser, self.org_b).get("/api/v1/properties/properties/")
        self.assertEqual(response.status_code, 200)


class CapabilityTests(DahooTestCase):
    def test_viewer_can_read_but_not_write(self):
        viewer = client_for(add_member(self.org_a, role="VIEWER"))
        self.assertEqual(viewer.get("/api/v1/properties/properties/").status_code, 200)
        response = viewer.post("/api/v1/properties/properties/", {"name": "X", "address": "a", "city": "Dakar"})
        self.assertEqual(response.status_code, 403)

    def test_accountant_cannot_manage_team(self):
        accountant = client_for(add_member(self.org_a, role="ACCOUNTANT"))
        response = accountant.post(
            "/api/v1/organizations/members/", {"phone": self.admin_b.phone, "role": "VIEWER"}
        )
        self.assertEqual(response.status_code, 403)

    def test_me_capabilities_reflect_role(self):
        viewer = add_member(self.org_a, role="VIEWER")
        data = client_for(viewer).get("/api/v1/users/me/capabilities/").json()
        self.assertEqual(data["role"], "VIEWER")
        self.assertEqual(set(data["capabilities"]), SYSTEM_ROLES["VIEWER"]["capabilities"])

    def test_me_lists_memberships(self):
        data = self.api_a.get("/api/v1/users/me/").json()
        self.assertEqual(data["memberships"][0]["organization_id"], self.org_a.id)
        self.assertEqual(data["memberships"][0]["role"], "ORG_ADMIN")

    def test_roles_endpoint_is_mounted(self):
        response = self.api_a.get("/api/v1/access/roles/")
        self.assertEqual(response.status_code, 200)


class ReferenceDataTests(DahooTestCase):
    def test_reference_data_is_read_only_for_clients(self):
        self.assertEqual(self.api_a.get("/api/v1/payments/methods/").status_code, 200)
        response = self.api_a.post("/api/v1/payments/methods/", {"code": "X", "label": "Hack"})
        self.assertEqual(response.status_code, 403)
        response = self.api_a.post("/api/v1/subscriptions/plans/", {"name": "Gratuit", "billing_type": "MONTHLY"})
        self.assertEqual(response.status_code, 403)

    def test_staff_can_manage_reference_data(self):
        staff = client_for(make_user(is_staff=True))
        response = staff.post("/api/v1/payments/methods/", {"code": "OM", "label": "Orange Money"})
        self.assertEqual(response.status_code, 201)


class OrganizationTeamTests(DahooTestCase):
    def test_add_new_member_creates_account(self):
        response = self.api_a.post(
            "/api/v1/organizations/members/",
            {"phone": "+221771234567", "first_name": "Moussa", "last_name": "Fall", "password": "Motdepasse!2026", "role": "MANAGER"},
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["role"], "MANAGER")

    def test_new_member_requires_identity(self):
        response = self.api_a.post("/api/v1/organizations/members/", {"phone": "+221779999999", "role": "MANAGER"})
        self.assertEqual(response.status_code, 400)

    def test_cannot_change_own_membership(self):
        own = self.admin_a.memberships.get()
        response = self.api_a.patch(f"/api/v1/organizations/members/{own.id}/", {"role": "VIEWER"})
        self.assertEqual(response.status_code, 400)

    def test_members_are_isolated(self):
        other = self.admin_b.memberships.get()
        self.assertEqual(self.api_a.get(f"/api/v1/organizations/members/{other.id}/").status_code, 404)

    def test_current_organization(self):
        response = self.api_a.patch("/api/v1/organizations/current/", {"city": "Thiès"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "Agence A")
