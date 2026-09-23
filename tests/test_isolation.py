"""Aucune donnée d'une organisation ne doit être visible ou utilisable depuis une autre."""

from analytics.models import FinancialSnapshot, Insight
from field_ops.models import FieldEvent, GuardianProfile
from listings.models import Listing
from maintenance.models import MaintenanceTicket
from payments.models import Payment

from .factories import DahooTestCase, make_lease, make_schedule, make_user, payment_method, results


class ReadIsolationTests(DahooTestCase):
    def setUp(self):
        super().setUp()
        self.lease = make_lease(self.org_a, created_by=self.admin_a)
        self.unit = self.lease.unit
        self.building = self.unit.building
        self.property = self.building.property
        self.schedule = make_schedule(self.lease)
        self.payment = Payment.objects.create(
            organization=self.org_a, payer=self.lease.tenant, recorded_by=self.admin_a,
            amount_paid=100, payment_method=payment_method(),
        )
        self.ticket = MaintenanceTicket.objects.create(unit=self.unit, reported_by=self.admin_a, description="Fuite")
        self.listing = Listing.objects.create(
            unit=self.unit, created_by=self.admin_a, title="T2", description="d", listing_type="RENT", price=1
        )
        self.guardian = GuardianProfile.objects.create(
            organization=self.org_a, user=make_user(), shift_start="08:00", shift_end="18:00"
        )
        self.event = FieldEvent.objects.create(
            building=self.building, recorded_by=self.admin_a, event_type="VISIT",
            description="d", occurred_at="2026-01-01T10:00:00Z",
        )
        FinancialSnapshot.objects.create(
            organization=self.org_a, month="2026-01-01", total_income=1000, total_expenses=1, net_result=999
        )
        Insight.objects.create(
            organization=self.org_a, target_type="unit", target_id=self.unit.id,
            insight_type="PAYMENT_RISK", score=0.9, explanation="Retards répétés",
        )

    def test_details_are_hidden_from_other_organization(self):
        urls = [
            f"/api/v1/properties/properties/{self.property.id}/",
            f"/api/v1/properties/buildings/{self.building.id}/",
            f"/api/v1/properties/units/{self.unit.id}/",
            f"/api/v1/properties/properties/{self.property.id}/buildings/",
            f"/api/v1/properties/buildings/{self.building.id}/units/",
            f"/api/v1/leases/{self.lease.id}/",
            f"/api/v1/payments/schedules/{self.schedule.id}/",
            f"/api/v1/payments/payments/{self.payment.id}/",
            f"/api/v1/maintenance/tickets/{self.ticket.id}/",
            f"/api/v1/maintenance/tickets/{self.ticket.id}/logs/",
            f"/api/v1/listings/{self.listing.id}/",
            f"/api/v1/listings/{self.listing.id}/interests/",
            f"/api/v1/field-ops/guardians/{self.guardian.id}/",
            f"/api/v1/field-ops/events/{self.event.id}/",
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.api_a.get(url).status_code, 200)
                self.assertEqual(self.api_b.get(url).status_code, 404)

    def test_lists_are_filtered(self):
        urls = [
            "/api/v1/properties/properties/",
            "/api/v1/leases/",
            "/api/v1/payments/schedules/",
            "/api/v1/payments/payments/",
            "/api/v1/maintenance/tickets/",
            "/api/v1/listings/",
            "/api/v1/field-ops/guardians/",
            "/api/v1/field-ops/events/",
            "/api/v1/analytics/snapshots/",
            "/api/v1/analytics/insights/",
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(len(results(self.api_a.get(url))), 1)
                self.assertEqual(results(self.api_b.get(url)), [])

    def test_actions_on_foreign_objects_are_refused(self):
        actions = [
            (f"/api/v1/leases/{self.lease.id}/activate/", {}),
            (f"/api/v1/properties/units/{self.unit.id}/status/", {"status": "MAINTENANCE"}),
            (f"/api/v1/maintenance/tickets/{self.ticket.id}/status/", {"status": "CLOSED"}),
            (f"/api/v1/listings/{self.listing.id}/publish/", {}),
            (f"/api/v1/payments/payments/{self.payment.id}/allocate/", {"allocations": []}),
        ]
        for url, payload in actions:
            with self.subTest(url=url):
                self.assertEqual(self.api_b.post(url, payload, format="json").status_code, 404)
        self.assertEqual(self.api_b.delete(f"/api/v1/properties/properties/{self.property.id}/").status_code, 404)


class WriteIsolationTests(DahooTestCase):
    """Référencer un objet d'une autre organisation à la création est rejeté (400)."""

    def setUp(self):
        super().setUp()
        self.lease_a = make_lease(self.org_a)
        self.unit_a = self.lease_a.unit
        self.schedule_a = make_schedule(self.lease_a)

    def assertRejected(self, url, payload, field):
        response = self.api_b.post(url, payload, format="json")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn(field, response.json())

    def test_lease_on_foreign_unit(self):
        self.assertRejected(
            "/api/v1/leases/",
            {"unit": self.unit_a.id, "tenant": self.admin_b.id, "start_date": "2026-01-01", "rent_amount": "1"},
            "unit",
        )

    def test_listing_on_foreign_unit(self):
        self.assertRejected(
            "/api/v1/listings/",
            {"unit": self.unit_a.id, "title": "t", "description": "d", "listing_type": "RENT", "price": "1"},
            "unit",
        )

    def test_ticket_on_foreign_unit(self):
        self.assertRejected("/api/v1/maintenance/tickets/", {"unit": self.unit_a.id, "description": "d"}, "unit")

    def test_field_event_on_foreign_building(self):
        self.assertRejected(
            "/api/v1/field-ops/events/",
            {"building": self.unit_a.building_id, "event_type": "VISIT", "description": "d", "occurred_at": "2026-01-01T10:00:00Z"},
            "building",
        )

    def test_schedule_on_foreign_lease(self):
        self.assertRejected(
            "/api/v1/payments/schedules/",
            {"lease_contract": self.lease_a.id, "schedule_type": "RENT", "due_date": "2026-02-01", "amount_due": "10"},
            "lease_contract",
        )

    def test_payment_allocated_to_foreign_schedule(self):
        lease_b = make_lease(self.org_b)
        self.assertRejected(
            "/api/v1/payments/payments/",
            {
                "payer": lease_b.tenant_id, "amount_paid": "10", "payment_method": payment_method().id,
                "allocations": [{"schedule": self.schedule_a.id, "amount": "10"}],
            },
            "allocations",
        )

    def test_guardian_on_foreign_building(self):
        self.assertRejected(
            "/api/v1/field-ops/guardians/",
            {"user": make_user().id, "shift_start": "08:00", "shift_end": "18:00", "buildings": [self.unit_a.building_id]},
            "buildings",
        )
