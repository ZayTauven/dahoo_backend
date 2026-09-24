from .factories import PASSWORD, DahooTestCase, make_user

LOGIN_URL = "/api/v1/users/login/"


class LoginTests(DahooTestCase):
    def test_login_with_phone(self):
        response = self.client.post(LOGIN_URL, {"phone": self.admin_a.phone, "password": PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.json())

    def test_wrong_password(self):
        response = self.client.post(LOGIN_URL, {"phone": self.admin_a.phone, "password": "faux"})
        self.assertEqual(response.status_code, 400)

    def test_login_is_throttled(self):
        codes = [
            self.client.post(LOGIN_URL, {"phone": self.admin_a.phone, "password": "faux"}).status_code
            for _ in range(11)
        ]
        self.assertEqual(codes[-1], 429)

    def test_access_token_works_end_to_end(self):
        token = self.client.post(LOGIN_URL, {"phone": self.admin_a.phone, "password": PASSWORD}).json()["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(self.client.get("/api/v1/properties/properties/").status_code, 200)


class AdminLoginTests(DahooTestCase):
    """La page de connexion de l'admin Django transmet le numéro sous le nom « username »."""

    def setUp(self):
        super().setUp()
        self.staff = make_user(is_staff=True)

    def admin_login(self, username, password=PASSWORD):
        self.client.post("/admin/login/", {"username": username, "password": password})
        return self.client.get("/admin/").status_code

    def test_staff_can_log_in_to_admin(self):
        self.assertEqual(self.admin_login(self.staff.phone), 200)

    def test_admin_accepts_local_number_format(self):
        local = self.staff.phone.removeprefix("+221")
        self.assertEqual(self.admin_login(f"{local[:2]} {local[2:5]} {local[5:7]} {local[7:]}"), 200)

    def test_admin_rejects_wrong_password(self):
        self.assertEqual(self.admin_login(self.staff.phone, "faux"), 302)
