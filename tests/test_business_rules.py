"""Règles de gestion verrouillées avant le MVP (audit du 2026-11-25)."""

from decimal import Decimal

from leases.models import LeaseContract
from listings.models import Listing
from maintenance.models import MaintenanceTicket
from payments.models import Payment, PaymentAllocation, PaymentSchedule
from properties.models import Property

from .factories import (
    DahooTestCase, add_member, client_for, make_lease, make_listing, make_owner, make_schedule, make_tenant,
    make_unit, payment_method,
)

SCHEDULES = "/api/v1/payments/schedules/"
PAYMENTS = "/api/v1/payments/payments/"


class AllocationRulesTests(DahooTestCase):
    def setUp(self):
        super().setUp()
        self.lease = make_lease(self.org_a, status="ACTIVE", tenant=make_tenant(self.org_a))
        self.schedule = make_schedule(self.lease)

    def pay(self, lease, schedule, amount="150000"):
        return self.api_a.post(PAYMENTS, {
            "payer": lease.tenant_id, "amount_paid": amount, "payment_method": payment_method().id,
            "allocations": [{"schedule": schedule.id, "amount": amount}],
        }, format="json")

    def test_cannot_settle_another_tenants_schedule(self):
        other = make_lease(self.org_a, status="ACTIVE", tenant=make_tenant(self.org_a))
        response = self.pay(other, self.schedule)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Payment.objects.exists())

    def test_paid_schedule_cannot_be_deleted(self):
        self.pay(self.lease, self.schedule)
        response = self.api_a.delete(f"{SCHEDULES}{self.schedule.id}/")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(PaymentAllocation.objects.count(), 1)

    def test_unpaid_schedule_can_be_deleted(self):
        self.assertEqual(self.api_a.delete(f"{SCHEDULES}{self.schedule.id}/").status_code, 204)

    def test_changing_the_amount_recomputes_is_paid(self):
        self.pay(self.lease, self.schedule)
        response = self.api_a.patch(f"{SCHEDULES}{self.schedule.id}/", {"amount_due": "200000"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(response.json()["is_paid"])
        self.assertTrue(self.api_a.patch(f"{SCHEDULES}{self.schedule.id}/", {"amount_due": "150000"}).json()["is_paid"])

    def test_amount_cannot_go_below_what_was_paid(self):
        self.pay(self.lease, self.schedule, "100000")
        response = self.api_a.patch(f"{SCHEDULES}{self.schedule.id}/", {"amount_due": "99999"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("amount_due", response.json())

    def test_paid_schedule_keeps_its_contract(self):
        self.pay(self.lease, self.schedule)
        other = make_lease(self.org_a, status="ACTIVE")
        response = self.api_a.patch(f"{SCHEDULES}{self.schedule.id}/", {"lease_contract": other.id})
        self.assertEqual(response.status_code, 400)

    def test_cancelled_payment_reopens_its_schedules(self):
        payment = self.pay(self.lease, self.schedule).json()
        self.assertEqual(self.api_a.post(f"{PAYMENTS}{payment['id']}/cancel/", {}).status_code, 400)
        response = self.api_a.post(f"{PAYMENTS}{payment['id']}/cancel/", {"reason": "Saisi deux fois"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNotNone(response.json()["cancelled_at"])
        self.schedule.refresh_from_db()
        self.assertFalse(self.schedule.is_paid)
        # Ni seconde annulation, ni nouvelle affectation.
        self.assertEqual(self.api_a.post(f"{PAYMENTS}{payment['id']}/cancel/", {"reason": "x"}).status_code, 400)
        again = self.api_a.post(
            f"{PAYMENTS}{payment['id']}/allocate/", {"allocations": [{"schedule": self.schedule.id, "amount": "1"}]}, format="json"
        )
        self.assertEqual(again.status_code, 400)

    def test_cancelled_payment_leaves_the_dashboard(self):
        payment = self.pay(self.lease, self.schedule).json()
        dashboard = lambda: self.api_a.get("/api/v1/analytics/dashboard/").json()["finance"]
        self.assertEqual(Decimal(dashboard()["period_collected"]), Decimal("150000"))
        self.api_a.post(f"{PAYMENTS}{payment['id']}/cancel/", {"reason": "Erreur"})
        self.assertEqual(Decimal(dashboard()["period_collected"]), 0)

    def test_cancel_needs_its_capability(self):
        payment = self.pay(self.lease, self.schedule).json()
        viewer = client_for(add_member(self.org_a, role="VIEWER"))
        self.assertEqual(viewer.post(f"{PAYMENTS}{payment['id']}/cancel/", {"reason": "x"}).status_code, 403)
        self.assertEqual(self.api_b.post(f"{PAYMENTS}{payment['id']}/cancel/", {"reason": "x"}).status_code, 404)


class UnitAndLeaseRulesTests(DahooTestCase):
    def status(self, unit, value):
        return self.api_a.post(f"/api/v1/properties/units/{unit.id}/status/", {"status": value})

    def test_unit_under_active_lease_keeps_its_status(self):
        lease = make_lease(self.org_a, unit=make_unit(self.org_a, status="RENTED"), status="ACTIVE")
        for value in ("FREE", "MAINTENANCE", "SOLD"):
            with self.subTest(value=value):
                self.assertEqual(self.status(lease.unit, value).status_code, 400)
                patched = self.api_a.patch(f"/api/v1/properties/units/{lease.unit_id}/", {"status": value})
                self.assertEqual(patched.status_code, 400)

    def test_rented_comes_from_a_lease_only(self):
        self.assertEqual(self.status(make_unit(self.org_a), "RENTED").status_code, 400)
        self.assertEqual(self.status(make_unit(self.org_a), "MAINTENANCE").status_code, 200)

    def test_lease_cannot_start_on_a_sold_or_closed_unit(self):
        for value in ("SOLD", "MAINTENANCE"):
            with self.subTest(value=value):
                lease = make_lease(self.org_a, unit=make_unit(self.org_a, status=value))
                self.assertEqual(self.api_a.post(f"/api/v1/leases/{lease.id}/activate/").status_code, 400)

    def test_draft_lease_can_be_corrected(self):
        lease = make_lease(self.org_a, tenant=make_tenant(self.org_a))
        other = make_tenant(self.org_a, first_name="Khady", last_name="Ba")
        response = self.api_a.patch(f"/api/v1/leases/{lease.id}/", {"rent_amount": "175000", "tenant": other.id})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["tenant_name"], "Khady Ba")
        self.assertEqual(response.json()["rent_amount"], "175000.00")

    def test_active_lease_accepts_an_amendment_only(self):
        lease = make_lease(self.org_a, status="ACTIVE", tenant=make_tenant(self.org_a))
        url = f"/api/v1/leases/{lease.id}/"
        self.assertEqual(self.api_a.patch(url, {"rent_amount": "160000", "end_date": "2027-12-31"}).status_code, 200)
        self.assertEqual(self.api_a.patch(url, {"start_date": "2026-02-01"}).status_code, 400)
        self.assertEqual(self.api_a.patch(url, {"end_date": "2025-12-31"}).status_code, 400)
        LeaseContract.objects.filter(pk=lease.pk).update(status="COMPLETED")
        self.assertEqual(self.api_a.patch(url, {"rent_amount": "1"}).status_code, 400)

    def test_deposit_is_due_at_activation_and_dropped_if_never_paid(self):
        lease = make_lease(self.org_a)
        LeaseContract.objects.filter(pk=lease.pk).update(deposit_amount=Decimal("300000"))
        self.api_a.post(f"/api/v1/leases/{lease.id}/activate/", {"auto_schedules": False, "with_deposit": True}, format="json")
        deposit = PaymentSchedule.objects.get(lease_contract=lease, schedule_type="DEPOSIT")
        self.assertEqual(deposit.amount_due, Decimal("300000"))
        self.api_a.post(f"/api/v1/leases/{lease.id}/cancel/")
        self.assertFalse(PaymentSchedule.objects.filter(pk=deposit.pk).exists())

    def test_property_owner_belongs_to_the_agency(self):
        unit = make_unit(self.org_a)
        url = f"/api/v1/properties/properties/{unit.building.property_id}/"
        self.assertEqual(self.api_a.patch(url, {"owner": make_owner(self.org_b).id}).status_code, 400)
        mine = make_owner(self.org_a)
        response = self.api_a.patch(url, {"owner": mine.id, "commission_rate": "10"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["owner_name"], "Fatou Ndiaye")
        self.assertEqual(self.api_a.patch(url, {"commission_rate": "101"}).status_code, 400)
        # Un bailleur qui a des biens ne se supprime pas.
        self.assertEqual(self.api_a.delete(f"/api/v1/owners/{mine.id}/").status_code, 409)

    def test_unit_with_past_leases_explains_why_it_stays(self):
        lease = make_lease(self.org_a, status="COMPLETED")
        response = self.api_a.delete(f"/api/v1/properties/units/{lease.unit_id}/")
        self.assertEqual(response.status_code, 409)
        self.assertIn("même terminés", response.json()["detail"])


class ListingAndTicketRulesTests(DahooTestCase):
    def test_rented_or_sold_unit_cannot_be_published(self):
        for status in ("RENTED", "SOLD"):
            listing = make_listing(self.org_a, unit=make_unit(self.org_a, status=status), status="DRAFT")
            self.assertEqual(self.api_a.post(f"/api/v1/listings/{listing.id}/publish/").status_code, 400)

    def test_one_published_listing_per_unit(self):
        first = make_listing(self.org_a)
        second = make_listing(self.org_a, unit=first.unit, status="DRAFT")
        self.assertEqual(self.api_a.post(f"/api/v1/listings/{second.id}/publish/").status_code, 400)

    def test_listing_can_be_closed_for_good(self):
        listing = make_listing(self.org_a)
        self.assertEqual(self.api_a.post(f"/api/v1/listings/{listing.id}/close/").json()["status"], "CLOSED")
        self.assertEqual(self.api_a.post(f"/api/v1/listings/{listing.id}/publish/").status_code, 400)

    def test_activating_a_lease_closes_the_rental_listing(self):
        listing = make_listing(self.org_a)
        lease = make_lease(self.org_a, unit=listing.unit)
        self.api_a.post(f"/api/v1/leases/{lease.id}/activate/")
        self.assertEqual(Listing.objects.get(pk=listing.pk).status, "CLOSED")

    def test_closed_ticket_stays_closed(self):
        ticket = MaintenanceTicket.objects.create(unit=make_unit(self.org_a), reported_by=self.admin_a, description="Fuite")
        url = f"/api/v1/maintenance/tickets/{ticket.id}/status/"
        self.assertEqual(self.api_a.post(url, {"status": "RESOLVED"}).json()["next_statuses"], ["IN_PROGRESS", "CLOSED"])
        self.assertEqual(self.api_a.post(url, {"status": "IN_PROGRESS"}).status_code, 200)
        self.assertEqual(self.api_a.post(url, {"status": "CLOSED"}).status_code, 200)
        self.assertEqual(self.api_a.post(url, {"status": "OPEN"}).status_code, 400)

    def test_demo_request_phone_is_normalized(self):
        response = self.api_a.post("/api/v1/public/demo-requests/", {
            "agency_name": "Agence", "contact_name": "Awa", "phone": "77 123 45 67", "units_range": "1-20",
        })
        self.assertEqual(response.status_code, 201, response.content)
        from public.models import DemoRequest
        self.assertEqual(DemoRequest.objects.get().phone, "+221771234567")


class AccountingNamesTests(DahooTestCase):
    def test_dashboard_uses_the_agencys_own_tenant_name(self):
        """Le compte est partagé entre agences : le nom saisi par l'une ne s'affiche pas chez l'autre."""
        make_tenant(self.org_b, phone="+221761112233", first_name="Nom", last_name="Chez B")
        tenant = make_tenant(self.org_a, phone="+221761112233", first_name="Nom", last_name="Chez A")
        schedule = make_schedule(make_lease(self.org_a, status="ACTIVE", tenant=tenant))
        self.assertIsNotNone(schedule)
        late = self.api_a.get("/api/v1/analytics/dashboard/").json()["finance"]["late"]
        self.assertEqual(late[0]["tenant"], "Nom Chez A")
        self.assertTrue(Property.objects.filter(organization=self.org_a).exists())
