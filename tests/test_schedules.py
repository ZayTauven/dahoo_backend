from datetime import date
from decimal import Decimal
from unittest.mock import patch

from leases.models import LeaseContract
from notifications.services import sync_reminders
from payments.models import Payment, PaymentSchedule
from payments.schedules import lease_periods
from payments.services import allocate_payment

from .factories import DahooTestCase, make_lease, payment_method

TODAY = date(2026, 10, 5)
today = patch("payments.schedules.timezone.localdate", return_value=TODAY)


def lease_terms(**fields):
    defaults = {
        "start_date": date(2026, 1, 1), "end_date": None, "rent_amount": Decimal("150000"),
        "charges_amount": Decimal("0"), "payment_frequency": "MONTHLY", "due_day": 5,
    }
    return LeaseContract(**{**defaults, **fields})


def dues(lease, until):
    return [(period.due_date, period.amount) for period in lease_periods(lease, until=until)]


class LeasePeriodTests(DahooTestCase):
    def test_monthly_rent_is_due_on_due_day(self):
        lease = lease_terms(charges_amount=Decimal("10000"))
        self.assertEqual(
            dues(lease, date(2026, 3, 31)),
            [(date(2026, 1, 5), 160000), (date(2026, 2, 5), 160000), (date(2026, 3, 5), 160000)],
        )

    def test_first_month_is_prorated_and_due_on_move_in(self):
        lease = lease_terms(start_date=date(2026, 1, 15))
        # 17 jours occupés sur 31.
        self.assertEqual(dues(lease, date(2026, 2, 28)), [(date(2026, 1, 15), 82258), (date(2026, 2, 5), 150000)])

    def test_last_month_is_prorated_and_nothing_after_the_end(self):
        lease = lease_terms(end_date=date(2026, 3, 10))
        self.assertEqual(dues(lease, date(2026, 12, 31))[-1], (date(2026, 3, 5), 48387))
        self.assertEqual(len(dues(lease, date(2026, 12, 31))), 3)

    def test_quarterly_rent_covers_three_months(self):
        lease = lease_terms(payment_frequency="QUARTERLY", rent_amount=Decimal("100000"), charges_amount=Decimal("10000"))
        self.assertEqual(dues(lease, date(2026, 6, 30)), [(date(2026, 1, 5), 330000), (date(2026, 4, 5), 330000)])


@today
class AutoSchedulesApiTests(DahooTestCase):
    def make_draft(self, start=date(2026, 7, 1), **fields):
        lease = make_lease(self.org_a)
        LeaseContract.objects.filter(pk=lease.pk).update(start_date=start, **fields)
        lease.refresh_from_db()
        return lease

    def due_dates(self, lease):
        return list(lease.schedules.order_by("due_date").values_list("due_date", flat=True))

    def test_activation_creates_rents_up_to_one_month_ahead(self, _):
        lease = self.make_draft()
        response = self.api_a.post(f"/api/v1/leases/{lease.id}/activate/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["created_schedules"], 5)
        self.assertTrue(response.json()["auto_schedules"])
        self.assertEqual(self.due_dates(lease)[0], date(2026, 7, 5))
        self.assertEqual(self.due_dates(lease)[-1], date(2026, 11, 5))

    def test_activation_can_skip_past_periods(self, _):
        lease = self.make_draft()
        response = self.api_a.post(
            f"/api/v1/leases/{lease.id}/activate/", {"schedules_from": "2026-10-01"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.due_dates(lease), [date(2026, 10, 5), date(2026, 11, 5)])

    def test_activation_without_schedules(self, _):
        lease = self.make_draft()
        response = self.api_a.post(f"/api/v1/leases/{lease.id}/activate/", {"auto_schedules": False}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(response.json()["auto_schedules"])
        self.assertEqual(self.due_dates(lease), [])

    def test_schedules_from_must_be_within_the_lease(self, _):
        lease = self.make_draft(end_date=date(2027, 6, 30))
        for value in ("2026-06-30", "2027-07-01"):
            with self.subTest(value=value):
                response = self.api_a.post(f"/api/v1/leases/{lease.id}/activate/", {"schedules_from": value}, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertIn("schedules_from", response.json())
        lease.refresh_from_db()
        self.assertEqual(lease.status, "DRAFT")

    def test_periods_already_billed_are_skipped(self, _):
        lease = self.make_draft()
        PaymentSchedule.objects.create(
            organization=self.org_a, lease_contract=lease, schedule_type="RENT",
            due_date=date(2026, 8, 10), amount_due=Decimal("150000"),
        )
        self.api_a.post(f"/api/v1/leases/{lease.id}/activate/", {}, format="json")
        self.assertEqual(len(self.due_dates(lease)), 5)
        self.assertIn(date(2026, 8, 10), self.due_dates(lease))
        self.assertNotIn(date(2026, 8, 5), self.due_dates(lease))

    def test_reminder_sync_extends_the_schedule_without_duplicates(self, _):
        lease = self.make_draft()
        self.api_a.post(f"/api/v1/leases/{lease.id}/activate/", {}, format="json")
        sync_reminders(self.org_a, today=TODAY, force=True)
        self.assertEqual(len(self.due_dates(lease)), 5)
        sync_reminders(self.org_a, today=date(2026, 11, 20), force=True)
        self.assertEqual(self.due_dates(lease)[-1], date(2026, 12, 5))
        self.assertEqual(len(self.due_dates(lease)), 6)

    def test_termination_drops_unpaid_future_rents_only(self, _):
        lease = self.make_draft()
        self.api_a.post(f"/api/v1/leases/{lease.id}/activate/", {}, format="json")
        november = lease.schedules.get(due_date=date(2026, 11, 5))
        payment = Payment.objects.create(
            organization=self.org_a, payer=lease.tenant, recorded_by=self.admin_a,
            amount_paid=Decimal("1000"), payment_method=payment_method(),
        )
        allocate_payment(payment, [{"schedule": november, "amount": Decimal("1000")}])
        lease.schedules.filter(due_date=date(2026, 9, 5)).update(due_date=date(2026, 10, 20))  # à venir, sans paiement

        self.api_a.post(f"/api/v1/leases/{lease.id}/terminate/")
        remaining = self.due_dates(lease)
        self.assertNotIn(date(2026, 10, 20), remaining)
        self.assertIn(date(2026, 11, 5), remaining)  # un paiement y est affecté
        self.assertIn(date(2026, 10, 5), remaining)

    def test_preview_offers_current_period_for_old_leases(self, _):
        lease = self.make_draft()
        response = self.api_a.get(f"/api/v1/leases/{lease.id}/auto-schedules/")
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data["from_start"]["count"], 5)
        self.assertEqual(data["from_start"]["total"], "750000.00")
        self.assertEqual(data["from_current"]["schedules_from"], "2026-10-01")
        self.assertEqual(data["from_current"]["count"], 2)
        self.assertEqual(lease.schedules.count(), 0)  # un aperçu ne crée rien

    def test_preview_of_a_lease_starting_this_month(self, _):
        lease = self.make_draft(start=date(2026, 10, 20))
        data = self.api_a.get(f"/api/v1/leases/{lease.id}/auto-schedules/").json()
        self.assertIsNone(data["from_current"])
        self.assertEqual(data["from_start"]["first_due"], "2026-10-20")
        self.assertTrue(data["from_start"]["prorated"])

    def test_preview_offers_one_choice_when_past_rents_exist(self, _):
        lease = self.make_draft()
        for month in (7, 8, 9):
            PaymentSchedule.objects.create(
                organization=self.org_a, lease_contract=lease, schedule_type="RENT",
                due_date=date(2026, month, 5), amount_due=Decimal("150000"),
            )
        data = self.api_a.get(f"/api/v1/leases/{lease.id}/auto-schedules/").json()
        self.assertIsNone(data["from_current"])
        self.assertEqual(data["from_start"]["count"], 2)

    def test_enable_and_disable_on_an_active_lease(self, _):
        lease = self.make_draft()
        self.api_a.post(f"/api/v1/leases/{lease.id}/activate/", {"auto_schedules": False}, format="json")
        response = self.api_a.post(
            f"/api/v1/leases/{lease.id}/auto-schedules/", {"schedules_from": "2026-10-01"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["created_schedules"], 2)

        response = self.api_a.delete(f"/api/v1/leases/{lease.id}/auto-schedules/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["auto_schedules"])
        sync_reminders(self.org_a, today=date(2026, 12, 20), force=True)
        self.assertEqual(len(self.due_dates(lease)), 2)

    def test_draft_lease_cannot_enable_auto_schedules(self, _):
        lease = self.make_draft()
        response = self.api_a.post(f"/api/v1/leases/{lease.id}/auto-schedules/", {}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_other_agency_cannot_reach_the_lease(self, _):
        lease = self.make_draft()
        self.assertEqual(self.api_b.get(f"/api/v1/leases/{lease.id}/auto-schedules/").status_code, 404)
        self.assertEqual(self.api_b.post(f"/api/v1/leases/{lease.id}/auto-schedules/", {}, format="json").status_code, 404)


class LeaseDueDayTests(DahooTestCase):
    def test_due_day_is_limited_to_28(self):
        from .factories import make_tenant, make_unit

        response = self.api_a.post(
            "/api/v1/leases/",
            {"unit": make_unit(self.org_a).id, "tenant": make_tenant(self.org_a).id, "start_date": "2026-01-01",
             "rent_amount": "150000", "due_day": 31},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("due_day", response.json())
