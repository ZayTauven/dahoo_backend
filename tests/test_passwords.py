from organizations.models import Membership

from .factories import PASSWORD, DahooTestCase, add_member, client_for, make_user

LOGIN = "/api/v1/users/login/"
NEW = "Nouveau!Passe2027"


class PasswordTests(DahooTestCase):
    def login(self, user, password):
        return self.client.post(LOGIN, {"phone": user.phone, "password": password})

    def reset_url(self, user, organization=None):
        membership = Membership.objects.get(user=user, organization=organization or self.org_a)
        return f"/api/v1/organizations/members/{membership.id}/reset-password/"

    def test_user_changes_own_password_and_old_sessions_close(self):
        tokens = self.login(self.admin_a, PASSWORD).json()
        url = "/api/v1/users/me/password/"
        self.assertEqual(self.api_a.post(url, {"current_password": "faux", "new_password": NEW}).status_code, 400)
        self.assertEqual(self.api_a.post(url, {"current_password": PASSWORD, "new_password": "123"}).status_code, 400)
        response = self.api_a.post(url, {"current_password": PASSWORD, "new_password": NEW})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.login(self.admin_a, NEW).status_code, 200)
        self.assertEqual(self.client.post("/api/v1/users/refresh/", {"refresh": tokens["refresh"]}).status_code, 401)
        self.assertEqual(self.client.post("/api/v1/users/refresh/", {"refresh": response.json()["refresh"]}).status_code, 200)

    def test_admin_resets_a_member(self):
        member = add_member(self.org_a, role="MANAGER")
        response = self.api_a.post(self.reset_url(member))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.login(member, response.json()["temporary_password"]).status_code, 200)

    def test_shared_or_platform_accounts_are_protected(self):
        shared = add_member(self.org_a, role="MANAGER")
        add_member(self.org_b, user=shared)
        staff = add_member(self.org_a, user=make_user(is_staff=True))
        for user in (shared, staff):
            with self.subTest(user=user.pk):
                self.assertEqual(self.api_a.post(self.reset_url(user)).status_code, 403)
                self.assertEqual(self.login(user, PASSWORD).status_code, 200)

    def test_rights(self):
        member = add_member(self.org_a, role="MANAGER")
        self.assertEqual(client_for(member).post(self.reset_url(self.admin_a)).status_code, 403)
        self.assertEqual(self.api_b.post(self.reset_url(member)).status_code, 404)
        self.assertEqual(self.api_a.post(self.reset_url(self.admin_a)).status_code, 400)

    def test_dahoo_team_resets_any_agency_member_but_not_its_own(self):
        dahoo = client_for(make_user(is_staff=True))
        membership = Membership.objects.get(user=self.admin_a)
        url = f"/api/v1/platform/organizations/{self.org_a.id}/members/{membership.id}/reset-password/"
        self.assertEqual(self.api_a.post(url).status_code, 403)
        self.assertEqual(dahoo.post(url).status_code, 200)
        staff = add_member(self.org_a, user=make_user(is_staff=True))
        own = Membership.objects.get(user=staff)
        self.assertEqual(
            dahoo.post(f"/api/v1/platform/organizations/{self.org_a.id}/members/{own.id}/reset-password/").status_code, 403
        )
