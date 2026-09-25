"""Apparence de l'espace agence (personnaliseur) : droits, validation stricte, cloisonnement."""

from .factories import DahooTestCase, add_member, client_for

URL = "/api/v1/organizations/current/"


class OrganizationThemeTests(DahooTestCase):
    def test_admin_saves_theme(self):
        theme = {"accent": "custom", "accent_custom": "#1e856c", "sidebar": "brand", "page": "compact"}
        response = self.api_a.patch(URL, {"theme": theme}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["theme"], {**theme, "accent_custom": "#1E856C"})
        self.org_a.refresh_from_db()
        self.assertEqual(self.org_a.theme["sidebar"], "brand")
        # Un nouvel envoi remplace l'ancien thème en entier (retour aux valeurs par défaut possible).
        self.api_a.patch(URL, {"theme": {}}, format="json")
        self.org_a.refresh_from_db()
        self.assertEqual(self.org_a.theme, {})

    def test_manager_cannot_change_theme(self):
        manager = add_member(self.org_a, role="MANAGER")
        response = client_for(manager).patch(URL, {"theme": {"sidebar": "dark"}}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_rejects_unknown_values(self):
        for theme in ({"sidebar": "rainbow"}, {"couleur": "rouge"}, {"accent": "custom"}, {"accent": "custom", "accent_custom": "red"}):
            response = self.api_a.patch(URL, {"theme": theme}, format="json")
            self.assertEqual(response.status_code, 400, theme)

    def test_theme_is_per_organization(self):
        self.api_a.patch(URL, {"theme": {"header": "dark"}}, format="json")
        self.assertEqual(self.api_b.get(URL).json()["theme"], {})

    def test_members_receive_agency_theme(self):
        self.api_a.patch(URL, {"theme": {"accent": "cobalt", "sidebar": "dark"}}, format="json")
        viewer = add_member(self.org_a, role="VIEWER")
        memberships = client_for(viewer).get("/api/v1/users/me/").json()["memberships"]
        self.assertEqual(memberships[0]["organization_theme"], {"accent": "cobalt", "sidebar": "dark"})
