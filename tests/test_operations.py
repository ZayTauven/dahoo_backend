"""Annonces, maintenance, terrain et quotas d'abonnement."""

from django.core.cache import cache
from rest_framework.test import APIClient

from listings.models import Listing, Prospect
from maintenance.models import MaintenanceTicket
from subscriptions.models import Subscription, SubscriptionPlan

from .factories import DahooTestCase, add_member, make_unit, make_user

PROSPECT = {"full_name": "Fatou Ndiaye", "phone": "+221770000001", "source": "site"}


class ListingTests(DahooTestCase):
    def setUp(self):
        super().setUp()
        self.listing = Listing.objects.create(
            unit=make_unit(self.org_a), created_by=self.admin_a,
            title="T2 Almadies", description="d", listing_type="RENT", price=300000,
        )
        self.public = APIClient()

    def interest(self, listing=None, prospect=PROSPECT):
        return self.public.post(
            f"/api/v1/listings/{(listing or self.listing).id}/interest/",
            {"prospect": prospect, "message": "Disponible ?"},
            format="json",
        )

    def test_publish_then_public_interest_without_account(self):
        self.assertEqual(self.api_a.post(f"/api/v1/listings/{self.listing.id}/publish/").status_code, 200)
        response = self.interest()
        self.assertEqual(response.status_code, 201, response.content)
        self.assertNotIn("prospect", response.json())

    def test_no_interest_on_unpublished_listing(self):
        self.assertEqual(self.interest().status_code, 404)

    def test_publish_twice_is_refused(self):
        self.api_a.post(f"/api/v1/listings/{self.listing.id}/publish/")
        self.assertEqual(self.api_a.post(f"/api/v1/listings/{self.listing.id}/publish/").status_code, 400)

    def test_status_is_not_writable_directly(self):
        self.api_a.patch(f"/api/v1/listings/{self.listing.id}/", {"status": "PUBLISHED"})
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, "DRAFT")

    def test_prospects_are_deduplicated_per_organization(self):
        self.api_a.post(f"/api/v1/listings/{self.listing.id}/publish/")
        other = Listing.objects.create(
            unit=make_unit(self.org_b), created_by=self.admin_b,
            title="Villa", description="d", listing_type="SALE", price=1, status="PUBLISHED",
        )
        self.interest()
        self.interest()
        self.interest(listing=other)
        self.assertEqual(Prospect.objects.filter(organization=self.org_a).count(), 1)
        self.assertEqual(Prospect.objects.filter(organization=self.org_b).count(), 1)
        interests = self.api_a.get(f"/api/v1/listings/{self.listing.id}/interests/").json()["results"]
        self.assertEqual(len(interests), 2)

    def test_public_interest_is_throttled(self):
        cache.clear()
        self.api_a.post(f"/api/v1/listings/{self.listing.id}/publish/")
        codes = [self.interest().status_code for _ in range(11)]
        self.assertEqual(codes[-1], 429)


class MaintenanceTests(DahooTestCase):
    def setUp(self):
        super().setUp()
        self.ticket = MaintenanceTicket.objects.create(
            unit=make_unit(self.org_a), reported_by=self.admin_a, description="Fuite"
        )

    def assign(self, user):
        return self.api_a.post(f"/api/v1/maintenance/tickets/{self.ticket.id}/assign/", {"assigned_to": user.id})

    def test_assign_to_member(self):
        technician = add_member(self.org_a, role="MANAGER")
        self.assertEqual(self.assign(technician).status_code, 201)

    def test_cannot_assign_outside_organization(self):
        self.assertEqual(self.assign(self.admin_b).status_code, 400)
        self.assertEqual(self.assign(make_user()).status_code, 400)

    def test_cannot_assign_to_member_active_only_elsewhere(self):
        user = add_member(self.org_b)
        add_member(self.org_a, user=user)
        user.memberships.filter(organization=self.org_a).update(is_active=False)
        self.assertEqual(self.assign(user).status_code, 400)

    def test_invalid_status(self):
        response = self.api_a.post(f"/api/v1/maintenance/tickets/{self.ticket.id}/status/", {"status": "DONE"})
        self.assertEqual(response.status_code, 400)

    def test_log_is_attributed(self):
        response = self.api_a.post(f"/api/v1/maintenance/tickets/{self.ticket.id}/logs/", {"message": "Plombier appelé"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["user"], self.admin_a.id)


class FieldOpsTests(DahooTestCase):
    def test_event_is_attributed_to_author(self):
        # Régression : recorded_by absent -> IntegrityError 500.
        unit = make_unit(self.org_a)
        response = self.api_a.post(
            "/api/v1/field-ops/events/",
            {"building": unit.building_id, "unit": unit.id, "event_type": "DELIVERY", "description": "Colis", "occurred_at": "2026-01-01T10:00:00Z"},
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["recorded_by"], self.admin_a.id)

    def test_unit_must_belong_to_building(self):
        unit, other = make_unit(self.org_a), make_unit(self.org_a)
        response = self.api_a.post(
            "/api/v1/field-ops/events/",
            {"building": other.building_id, "unit": unit.id, "event_type": "VISIT", "description": "d", "occurred_at": "2026-01-01T10:00:00Z"},
        )
        self.assertEqual(response.status_code, 400)


class QuotaTests(DahooTestCase):
    PROPERTY = {"name": "Résidence", "address": "Rue 1", "city": "Dakar"}

    def test_no_subscription_means_no_limit(self):
        for _ in range(3):
            self.assertEqual(self.api_a.post("/api/v1/properties/properties/", self.PROPERTY).status_code, 201)

    def test_plan_limit_is_enforced(self):
        plan = SubscriptionPlan.objects.create(name="Starter", billing_type="MONTHLY", price=10000, max_properties=1)
        Subscription.objects.create(organization=self.org_a, plan=plan, start_date="2026-01-01")
        self.assertEqual(self.api_a.post("/api/v1/properties/properties/", self.PROPERTY).status_code, 201)
        self.assertEqual(self.api_a.post("/api/v1/properties/properties/", self.PROPERTY).status_code, 400)
        # L'autre organisation n'est pas concernée.
        self.assertEqual(self.api_b.post("/api/v1/properties/properties/", self.PROPERTY).status_code, 201)

    def test_subscription_is_read_only_for_clients(self):
        plan = SubscriptionPlan.objects.create(name="Pro", billing_type="MONTHLY", price=50000)
        response = self.api_a.post("/api/v1/subscriptions/subscriptions/", {"plan": plan.id, "start_date": "2026-01-01"})
        self.assertEqual(response.status_code, 405)
