"""Tableau de bord de l'espace agence : calculs, cloisonnement, droits et paramètres."""

from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from analytics.dashboard import add_months, build_dashboard
from listings.models import Prospect, ProspectInterest
from maintenance.models import MaintenanceTicket
from payments.models import Payment, PaymentSchedule
from payments.services import allocate_payment

from .factories import DahooTestCase, add_member, client_for, make_lease, make_listing, make_unit, payment_method

URL = "/api/v1/analytics/dashboard/"


def schedule(lease, due, amount):
    return PaymentSchedule.objects.create(
        organization=lease.organization, lease_contract=lease, schedule_type="RENT", due_date=due, amount_due=Decimal(amount),
    )


def pay(lease, target, amount, paid_on):
    payment = Payment.objects.create(
        organization=lease.organization, payer=lease.tenant, recorded_by=lease.created_by,
        amount_paid=Decimal(amount), payment_method=payment_method(),
    )
    Payment.objects.filter(pk=payment.pk).update(payment_date=timezone.make_aware(timezone.datetime.combine(paid_on, timezone.datetime.min.time())))
    allocate_payment(payment, [{"schedule": target, "amount": Decimal(amount)}])


class DashboardTests(DahooTestCase):
    def setUp(self):
        super().setUp()
        self.today = timezone.localdate()
        month = self.today.replace(day=1)
        self.lease = make_lease(self.org_a, unit=make_unit(self.org_a, status="RENTED"), status="ACTIVE")
        make_unit(self.org_a, status="FREE")
        # Mois courant : 200 000 dus, 120 000 payés. Mois précédent : 200 000 dus, rien payé (en retard).
        self.current = schedule(self.lease, month, "200000")
        self.previous = schedule(self.lease, add_months(month, -1), "200000")
        pay(self.lease, self.current, "120000", month)

    def test_finance_figures(self):
        data = self.api_a.get(URL).json()
        finance = data["finance"]
        self.assertEqual(len(finance["monthly"]), 12)
        current = finance["monthly"][-1]
        self.assertEqual(current["month"], self.today.strftime("%Y-%m"))
        self.assertEqual(Decimal(current["expected"]), Decimal("200000"))
        self.assertEqual(Decimal(current["collected"]), Decimal("120000"))
        self.assertEqual(finance["this_month"]["rate"], 60.0)
        self.assertEqual(finance["overdue"]["count"], 1 + (self.current.due_date < self.today))
        self.assertEqual(finance["by_method"][0]["code"], "WAVE")
        self.assertEqual(finance["late"][0]["id"], self.previous.id)

    def test_portfolio_and_insights(self):
        data = self.api_a.get(URL).json()
        self.assertEqual(data["portfolio"]["units"], 2)
        self.assertEqual(data["portfolio"]["occupancy_rate"], 50.0)
        kinds = [item["kind"] for item in data["insights"]]
        self.assertIn("overdue", kinds)
        self.assertIn("vacancy", kinds)

    def test_organizations_are_isolated(self):
        other = make_lease(self.org_b, status="ACTIVE")
        schedule(other, self.today.replace(day=1), "999000")
        data = self.api_b.get(URL).json()
        self.assertEqual(Decimal(data["finance"]["monthly"][-1]["expected"]), Decimal("999000"))
        data = self.api_a.get(URL).json()
        self.assertEqual(Decimal(data["finance"]["monthly"][-1]["expected"]), Decimal("200000"))

    def test_six_months_and_invalid_values(self):
        self.assertEqual(len(self.api_a.get(URL, {"months": 6}).json()["finance"]["monthly"]), 6)
        self.assertEqual(len(self.api_a.get(URL, {"months": "abc"}).json()["finance"]["monthly"]), 12)

    def test_maintenance_and_listings(self):
        unit = self.lease.unit
        MaintenanceTicket.objects.create(unit=unit, reported_by=self.admin_a, priority="URGENT", status="OPEN", description="Fuite")
        done = MaintenanceTicket.objects.create(unit=unit, reported_by=self.admin_a, status="RESOLVED", description="Serrure")
        MaintenanceTicket.objects.filter(pk=done.pk).update(updated_at=done.created_at + timedelta(days=2))
        listing = make_listing(self.org_a)
        prospect = Prospect.objects.create(organization=self.org_a, full_name="Coumba Fall", phone="+221770001122", source="site")
        ProspectInterest.objects.create(listing=listing, prospect=prospect)

        data = self.api_a.get(URL).json()
        self.assertEqual(data["maintenance"]["open"], 1)
        self.assertEqual(data["maintenance"]["urgent_open"], 1)
        self.assertEqual(data["maintenance"]["avg_resolution_days"], 2.0)
        self.assertEqual(data["listings"]["interests_30d"], 1)
        self.assertEqual(data["listings"]["top_listings"][0]["interests"], 1)
        self.assertEqual(data["listings"]["recent_interests"][0]["prospect"], "Coumba Fall")

    def test_viewer_can_read_and_anonymous_cannot(self):
        viewer = add_member(self.org_a, role="VIEWER")
        self.assertEqual(client_for(viewer).get(URL).status_code, 200)
        self.assertIn(self.client.get(URL).status_code, (401, 403))

    def test_sections_follow_capabilities(self):
        data = build_dashboard(self.org_a, set(), today=date.today())
        for section in ("portfolio", "leases", "finance", "maintenance", "listings"):
            self.assertIsNone(data[section])
        self.assertEqual(data["insights"], [])
