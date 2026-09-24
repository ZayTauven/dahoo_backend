"""Correctifs issus de la recette de la refonte du front (remontés par les écrans de l'espace agence)."""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from maintenance.models import MaintenanceAssignment, MaintenanceLog, MaintenanceTicket
from payments.models import PaymentAllocation
from users.phone import normalize_phone

from .factories import (
    PASSWORD,
    DahooTestCase,
    add_member,
    make_lease,
    make_schedule,
    make_tenant,
    make_unit,
    make_user,
    payment_method,
    results,
)


class PhoneNormalizationTests(DahooTestCase):
    def test_formats_are_unified(self):
        for raw in ("+221 77 000 00 01", "00221770000001", "770000001", "77-000-00-01", "+221770000001"):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_phone(raw), "+221770000001")

    def test_login_accepts_spaced_number(self):
        user = make_user(phone="+221 77 555 44 33")
        self.assertEqual(user.phone, "+221775554433")
        response = self.client.post("/api/v1/users/login/", {"phone": "77 555 44 33", "password": PASSWORD})
        self.assertEqual(response.status_code, 200)

    def test_same_tenant_in_another_format_is_a_duplicate(self):
        self.api_a.post("/api/v1/leases/tenants/", {"phone": "+221771112299", "first_name": "A", "last_name": "B"})
        response = self.api_a.post("/api/v1/leases/tenants/", {"phone": "77 111 22 99", "first_name": "A", "last_name": "B"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("phone", response.json())

    def test_invalid_number_is_refused(self):
        response = self.api_a.post("/api/v1/leases/tenants/", {"phone": "12", "first_name": "A", "last_name": "B"})
        self.assertEqual(response.status_code, 400)

    def test_new_member_phone_is_normalized(self):
        response = self.api_a.post(
            "/api/v1/organizations/members/",
            {"phone": "76 123 45 67", "first_name": "Sokhna", "last_name": "Ba", "password": "Motdepasse!2026", "role": "MANAGER"},
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["user"]["phone"], "+221761234567")


class LeaseFixesTests(DahooTestCase):
    def test_completing_a_terminated_lease_keeps_the_new_occupant(self):
        first = make_lease(self.org_a)
        self.api_a.post(f"/api/v1/leases/{first.id}/activate/")
        self.api_a.post(f"/api/v1/leases/{first.id}/terminate/")
        second = make_lease(self.org_a, unit=first.unit)
        self.api_a.post(f"/api/v1/leases/{second.id}/activate/")
        self.assertEqual(self.api_a.post(f"/api/v1/leases/{first.id}/complete/").status_code, 200)
        first.unit.refresh_from_db()
        self.assertEqual(first.unit.status, "RENTED")

    def test_transition_message_uses_labels(self):
        lease = make_lease(self.org_a)
        message = str(self.api_a.post(f"/api/v1/leases/{lease.id}/terminate/").json()["status"])
        self.assertIn("Brouillon", message)
        self.assertIn("Résilié", message)
        self.assertNotIn("TERMINATED", message)

    def test_search_by_tenant_or_unit(self):
        tenant = make_tenant(self.org_a, first_name="Mariama", last_name="Kane")
        make_lease(self.org_a, tenant=tenant)
        make_lease(self.org_a)
        self.assertEqual(len(results(self.api_a.get("/api/v1/leases/?search=Mariama"))), 1)

    def test_not_found_message_is_french(self):
        response = self.api_a.get("/api/v1/leases/999999/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Élément introuvable.")


class ProtectedDeletionTests(DahooTestCase):
    def test_deleting_a_property_with_leases_is_a_clear_409(self):
        lease = make_lease(self.org_a)
        property_id = lease.unit.building.property_id
        response = self.api_a.delete(f"/api/v1/properties/properties/{property_id}/")
        self.assertEqual(response.status_code, 409)
        self.assertIn("baux", response.json()["detail"])

    def test_deleting_a_unit_with_leases_is_a_clear_409(self):
        lease = make_lease(self.org_a)
        response = self.api_a.delete(f"/api/v1/properties/units/{lease.unit_id}/")
        self.assertEqual(response.status_code, 409)


class MaintenanceFixesTests(DahooTestCase):
    def setUp(self):
        super().setUp()
        self.unit = make_unit(self.org_a)

    def ticket(self, priority, **fields):
        return MaintenanceTicket.objects.create(unit=self.unit, reported_by=self.admin_a, description="d", priority=priority, **fields)

    def test_priority_order_is_by_severity(self):
        for priority in ("HIGH", "LOW", "URGENT", "MEDIUM"):
            self.ticket(priority)
        rows = results(self.api_a.get("/api/v1/maintenance/tickets/?ordering=-priority_rank"))
        self.assertEqual([row["priority"] for row in rows], ["URGENT", "HIGH", "MEDIUM", "LOW"])

    def test_current_assignment_and_names(self):
        ticket = self.ticket("MEDIUM")
        technician = add_member(self.org_a, user=make_user(first_name="Ousmane", last_name="Sy"), role="MANAGER")
        MaintenanceAssignment.objects.create(ticket=ticket, assigned_to=self.admin_a, assigned_by=self.admin_a)
        MaintenanceAssignment.objects.create(ticket=ticket, assigned_to=technician, assigned_by=self.admin_a)
        MaintenanceLog.objects.create(ticket=ticket, user=self.admin_a, message="Passage prévu demain")
        data = self.api_a.get(f"/api/v1/maintenance/tickets/{ticket.id}/").json()
        self.assertEqual(data["assigned_to"], technician.id)
        self.assertEqual(data["assigned_to_name"], "Ousmane Sy")
        self.assertEqual(data["reported_by_name"], f"{self.admin_a.first_name} {self.admin_a.last_name}")
        logs = results(self.api_a.get(f"/api/v1/maintenance/tickets/{ticket.id}/logs/"))
        self.assertEqual(logs[0]["user_name"], f"{self.admin_a.first_name} {self.admin_a.last_name}")

    def test_unassigned_ticket(self):
        data = self.api_a.get(f"/api/v1/maintenance/tickets/{self.ticket('LOW').id}/").json()
        self.assertIsNone(data["assigned_to"])
        self.assertIsNone(data["assigned_to_name"])


class PaymentFixesTests(DahooTestCase):
    def setUp(self):
        super().setUp()
        self.lease = make_lease(self.org_a, status="ACTIVE")
        self.schedule = make_schedule(self.lease, amount="150000")

    def pay(self, **fields):
        body = {"payer": self.lease.tenant_id, "amount_paid": "50000", "payment_method": payment_method().id, **fields}
        return self.api_a.post("/api/v1/payments/payments/", body, format="json")

    def test_payment_date_can_be_in_the_past(self):
        yesterday = timezone.now() - timedelta(days=1)
        response = self.pay(payment_date=yesterday.isoformat())
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["payment_date"][:10], yesterday.date().isoformat())

    def test_payment_date_cannot_be_in_the_future(self):
        response = self.pay(payment_date=(timezone.now() + timedelta(days=2)).isoformat())
        self.assertEqual(response.status_code, 400)
        self.assertIn("payment_date", response.json())

    def test_schedule_shows_paid_and_remaining(self):
        payment = self.pay().json()
        PaymentAllocation.objects.create(payment_id=payment["id"], schedule=self.schedule, allocated_amount=Decimal("40000"))
        data = self.api_a.get(f"/api/v1/payments/schedules/{self.schedule.id}/").json()
        self.assertEqual(data["amount_paid"], "40000.00")
        self.assertEqual(data["remaining_amount"], "110000.00")

    def test_allocate_response_shape(self):
        payment = self.pay().json()
        response = self.api_a.post(
            f"/api/v1/payments/payments/{payment['id']}/allocate/",
            {"allocations": [{"schedule": self.schedule.id, "amount": "10000"}]},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.json()["allocations"]), 1)
