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

    def test_overdue_grouped_by_tenant(self):
        # Une deuxième échéance en retard sur le même bail : une seule ligne, deux échéances.
        schedule(self.lease, add_months(self.today.replace(day=1), -2), "150000")
        finance = self.api_a.get(URL).json()["finance"]
        groups = finance["overdue"]["by_tenant"]
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["lease_id"], self.lease.id)
        self.assertEqual(groups[0]["count"], finance["overdue"]["count"])
        self.assertEqual(Decimal(groups[0]["amount"]), Decimal(finance["overdue"]["amount"]))
        self.assertGreaterEqual(groups[0]["days_late"], 32)
        self.assertEqual(finance["this_month"]["payments"], 1)

    def test_unlisted_free_units(self):
        listings = self.api_a.get(URL).json()["listings"]
        self.assertEqual(listings["unlisted_count"], 1)
        self.assertEqual(len(listings["unlisted_units"]), 1)

    def test_listing_interests_count_ignores_photos(self):
        listing = make_listing(self.org_a)
        listing.photos.create(image="listings/2026/09/a.jpg")
        listing.photos.create(image="listings/2026/09/b.jpg")
        for index in range(2):
            prospect = Prospect.objects.create(organization=self.org_a, full_name=f"Prospect {index}", phone=f"+22177000990{index}", source="site")
            ProspectInterest.objects.create(listing=listing, prospect=prospect)
        rows = self.api_a.get("/api/v1/listings/").json()["results"]
        row = next(row for row in rows if row["id"] == listing.id)
        self.assertEqual(row["interests_count"], 2)
        self.assertEqual(row["photos_count"], 2)

    def test_insights_carry_context(self):
        data = self.api_a.get(URL).json()
        by_kind = {item["kind"]: item for item in data["insights"]}
        self.assertNotIn("collection", by_kind)
        overdue = by_kind["overdue"]
        self.assertIsNotNone(overdue["amount"])
        self.assertIn(data["finance"]["overdue"]["by_tenant"][0]["tenant"], overdue["meta"])
        vacancy = by_kind["vacancy"]
        self.assertEqual(vacancy["count"], 1)
        self.assertEqual(vacancy["title"], "1 lot libre sans annonce")

    def test_nav_counters(self):
        MaintenanceTicket.objects.create(unit=self.lease.unit, description="Fuite", priority="HIGH", reported_by=self.lease.tenant)
        data = self.api_a.get("/api/v1/analytics/counters/").json()
        self.assertEqual(data["overdue_schedules"], self.api_a.get(URL).json()["finance"]["overdue"]["count"])
        self.assertEqual(data["open_tickets"], 1)
        self.assertGreaterEqual(data["properties"], 1)
        viewer = add_member(self.org_a, role="VIEWER")
        self.assertEqual(client_for(viewer).get("/api/v1/analytics/counters/").status_code, 200)

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
