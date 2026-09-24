from django.test import override_settings

from .factories import DahooTestCase

LOGIN_URL = "/api/v1/users/login/"
KEY = "cle-de-test-du-front"


def as_front(ip=None, key=KEY):
    headers = {"HTTP_X_DAHOO_PROXY_KEY": key}
    if ip:
        headers["HTTP_X_DAHOO_CLIENT_IP"] = ip
    return headers


@override_settings(INTERNAL_PROXY_KEY=KEY)
class ProxyThrottlingTests(DahooTestCase):
    def failed_logins(self, count, **headers):
        return [
            self.client.post(LOGIN_URL, {"phone": self.admin_a.phone, "password": "faux"}, **headers).status_code
            for _ in range(count)
        ]

    def test_each_visitor_has_its_own_login_counter(self):
        self.assertEqual(self.failed_logins(11, **as_front("41.82.0.1"))[-1], 429)
        # Un autre visiteur relayé par le même serveur Next n'est pas bloqué.
        self.assertEqual(self.failed_logins(1, **as_front("41.82.0.2")), [400])

    def test_client_ip_header_is_ignored_without_key(self):
        # Sans clé, changer d'IP déclarée ne permet pas de contourner la limite.
        codes = [
            self.client.post(
                LOGIN_URL, {"phone": self.admin_a.phone, "password": "faux"}, HTTP_X_DAHOO_CLIENT_IP=f"10.0.0.{i}"
            ).status_code
            for i in range(11)
        ]
        self.assertEqual(codes[-1], 429)

    def test_wrong_key_is_not_trusted(self):
        self.assertEqual(self.failed_logins(11, **as_front("41.82.0.3", key="mauvaise"))[-1], 429)
        self.assertEqual(self.failed_logins(1, **as_front("41.82.0.4", key="mauvaise")), [429])

    def test_server_side_public_reads_are_not_throttled(self):
        codes = {self.client.get("/api/v1/public/stats/", **as_front()).status_code for _ in range(65)}
        self.assertEqual(codes, {200})

    def test_trusted_writes_without_ip_are_still_throttled(self):
        self.assertEqual(self.failed_logins(11, **as_front())[-1], 429)

    def test_anonymous_public_reads_stay_throttled(self):
        codes = [self.client.get("/api/v1/public/stats/").status_code for _ in range(61)]
        self.assertEqual(codes[-1], 429)

    @override_settings(INTERNAL_PROXY_KEY="")
    def test_disabled_when_no_key_configured(self):
        self.assertEqual(self.failed_logins(11, **as_front("41.82.0.5", key=""))[-1], 429)
