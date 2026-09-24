from datetime import timedelta

from django.test import override_settings
from django.utils import timezone

from organizations.models import Organization
from subscriptions.models import Subscription, SubscriptionPlan

from .factories import DahooTestCase, add_member, client_for, make_user

PROPERTY = {"name": "Résidence", "address": "Rue 1", "city": "Dakar"}
PROPERTIES_URL = "/api/v1/properties/properties/"


class TrialTests(DahooTestCase):
    def expire_trial(self, organization):
        organization.trial_ends_at = timezone.now() - timedelta(minutes=1)
        organization.save(update_fields=["trial_ends_at"])

    def subscribe(self, organization, **dates):
        plan = SubscriptionPlan.objects.create(name="Pro", billing_type="MONTHLY", price=50000)
        return Subscription.objects.create(organization=organization, plan=plan, **{"start_date": timezone.localdate(), **dates})

    @override_settings(TRIAL_DAYS=14)
    def test_new_organization_gets_trial(self):
        organization = Organization.objects.create(name="Nouvelle agence")
        remaining = organization.trial_ends_at - timezone.now()
        self.assertEqual(round(remaining.total_seconds() / 86400), 14)

    def test_status_is_exposed_to_front(self):
        data = self.api_a.get("/api/v1/users/me/").json()["memberships"][0]
        self.assertEqual(data["access_status"], "TRIAL")
        self.assertIn("trial_ends_at", data)
        self.assertEqual(self.api_a.get("/api/v1/organizations/current/").json()["access_status"], "TRIAL")

    def test_expired_trial_is_read_only(self):
        self.expire_trial(self.org_a)
        self.assertEqual(self.api_a.get(PROPERTIES_URL).status_code, 200)
        response = self.api_a.post(PROPERTIES_URL, PROPERTY)
        self.assertEqual(response.status_code, 402)
        self.assertIn("essai", response.json()["detail"])
        self.assertEqual(self.api_a.get("/api/v1/organizations/current/").json()["access_status"], "EXPIRED")
        # L'autre agence n'est pas concernée.
        self.assertEqual(self.api_b.post(PROPERTIES_URL, PROPERTY).status_code, 201)

    def test_active_subscription_unlocks_writes(self):
        self.expire_trial(self.org_a)
        self.subscribe(self.org_a)
        self.assertEqual(self.api_a.post(PROPERTIES_URL, PROPERTY).status_code, 201)
        self.assertEqual(self.api_a.get("/api/v1/organizations/current/").json()["access_status"], "ACTIVE")

    def test_ended_or_future_subscription_does_not_count(self):
        self.expire_trial(self.org_a)
        today = timezone.localdate()
        self.subscribe(self.org_a, start_date=today - timedelta(days=60), end_date=today - timedelta(days=1))
        self.subscribe(self.org_a, start_date=today + timedelta(days=1))
        self.assertEqual(self.api_a.post(PROPERTIES_URL, PROPERTY).status_code, 402)

    def test_suspended_subscription_does_not_count(self):
        self.expire_trial(self.org_a)
        subscription = self.subscribe(self.org_a)
        subscription.status = "SUSPENDED"
        subscription.save()
        self.assertEqual(self.api_a.post(PROPERTIES_URL, PROPERTY).status_code, 402)

    def test_forbidden_action_stays_403_when_expired(self):
        # Sans la capability, on répond 403 (droit) avant 402 (abonnement).
        self.expire_trial(self.org_a)
        viewer = client_for(add_member(self.org_a, role="VIEWER"))
        self.assertEqual(viewer.post(PROPERTIES_URL, PROPERTY).status_code, 403)

    def test_superuser_is_not_blocked(self):
        self.expire_trial(self.org_a)
        superuser = client_for(make_user(is_superuser=True, is_staff=True), self.org_a)
        self.assertEqual(superuser.post(PROPERTIES_URL, PROPERTY).status_code, 201)
