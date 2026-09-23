from .factories import PASSWORD, DahooTestCase

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
