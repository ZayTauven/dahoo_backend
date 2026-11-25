"""Le travail quotidien : loyers du mois, encaissement, relance, quittance, relevé du bailleur."""

from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase
from django.utils import timezone

from dahoo.french import amount_in_words, number_to_words
from leases.models import LeaseContract
from payments.models import Payment, PaymentSchedule, RentReminder
from payments.schedules import schedule_period
from properties.models import Property

from .factories import (
    DahooTestCase, add_member, client_for, make_lease, make_owner, make_schedule, make_tenant, make_unit,
    payment_method,
)

ROLL = "/api/v1/payments/rent-roll/"
COLLECT = "/api/v1/payments/collect/"


class FrenchNumbersTests(SimpleTestCase):
    def test_number_to_words(self):
        cases = {
            0: "zéro", 17: "dix-sept", 21: "vingt et un", 71: "soixante et onze", 80: "quatre-vingts",
            81: "quatre-vingt-un", 91: "quatre-vingt-onze", 99: "quatre-vingt-dix-neuf", 100: "cent",
            200: "deux cents", 201: "deux cent un", 1000: "mille", 80_000: "quatre-vingt mille",
            151_000: "cent cinquante et un mille", 200_000: "deux cent mille", 1_000_000: "un million",
            2_500_300: "deux millions cinq cent mille trois cents",
        }
        for number, words in cases.items():
            with self.subTest(number=number):
                self.assertEqual(number_to_words(number), words)

    def test_amount(self):
        self.assertEqual(amount_in_words(Decimal("150000")), "cent cinquante mille francs CFA")
        self.assertEqual(amount_in_words(2_000_000), "deux millions de francs CFA")


class RentWorkTestCase(DahooTestCase):
    def setUp(self):
        super().setUp()
        self.tenant = make_tenant(self.org_a, phone="+221761234567", first_name="Awa", last_name="Sow")
        self.lease = make_lease(self.org_a, status="ACTIVE", tenant=self.tenant, unit=make_unit(self.org_a, status="RENTED"))
        today = timezone.localdate()
        self.month = today.replace(day=1)
        self.previous = (self.month - timezone.timedelta(days=1)).replace(day=1)

    def schedule(self, due, amount="150000", kind="RENT"):
        return PaymentSchedule.objects.create(
            organization=self.org_a, lease_contract=self.lease, schedule_type=kind, due_date=due, amount_due=Decimal(amount)
        )

    def collect(self, amount, **fields):
        body = {"lease": self.lease.id, "amount": amount, "payment_method": payment_method().id, **fields}
        return self.api_a.post(COLLECT, body, format="json")


class RentRollTests(RentWorkTestCase):
    def test_one_row_per_lease_with_arrears(self):
        self.schedule(self.previous)
        self.schedule(self.month)
        data = self.api_a.get(ROLL).json()
        self.assertEqual(len(data["rows"]), 1)
        row = data["rows"][0]
        self.assertEqual(row["tenant_name"], "Awa Sow")
        self.assertEqual(row["status"], "LATE")
        self.assertEqual(Decimal(row["due"]), Decimal("150000"))
        self.assertEqual(Decimal(row["arrears"]), Decimal("150000"))
        self.assertEqual(Decimal(row["total_due"]), Decimal("300000"))
        self.assertEqual(data["counts"]["LATE"], 1)

    def test_month_parameter_and_isolation(self):
        self.schedule(date(2026, 3, 5))
        data = self.api_a.get(f"{ROLL}?month=2026-03").json()
        self.assertEqual(Decimal(data["expected"]), Decimal("150000"))
        self.assertEqual(self.api_b.get(f"{ROLL}?month=2026-03").json()["rows"], [])
        self.assertEqual(self.api_a.get(f"{ROLL}?month=2026-13").status_code, 400)

    def test_active_lease_without_schedule_is_listed(self):
        self.assertEqual(self.api_a.get(ROLL).json()["rows"][0]["status"], "NONE")


class CollectTests(RentWorkTestCase):
    def test_oldest_schedules_first_and_receipts(self):
        old, current = self.schedule(self.previous), self.schedule(self.month)
        response = self.collect("200000")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["receipts"], [old.id])
        old.refresh_from_db(), current.refresh_from_db()
        self.assertTrue(old.is_paid)
        self.assertFalse(current.is_paid)
        row = self.api_a.get(ROLL).json()["rows"][0]
        self.assertEqual(Decimal(row["paid"]), Decimal("50000"))

    def test_overpayment_stays_available(self):
        self.schedule(self.month)
        payment = Payment.objects.get(pk=self.collect("180000").json()["payment"]["id"])
        self.assertEqual(sum(a.allocated_amount for a in payment.allocations.all()), Decimal("150000"))

    def test_rights_and_isolation(self):
        viewer = client_for(add_member(self.org_a, role="VIEWER"))
        body = {"lease": self.lease.id, "amount": "1", "payment_method": payment_method().id}
        self.assertEqual(viewer.post(COLLECT, body).status_code, 403)
        self.assertEqual(self.api_b.post(COLLECT, body).status_code, 400)

    def test_draft_lease_is_refused(self):
        LeaseContract.objects.filter(pk=self.lease.pk).update(status="DRAFT")
        self.assertEqual(self.collect("1").status_code, 400)


class ReminderTests(RentWorkTestCase):
    URL = "/api/v1/payments/reminders/"

    def test_reminder_is_traced_with_a_whatsapp_link(self):
        self.schedule(self.previous)
        response = self.api_a.post(self.URL, {"lease": self.lease.id})
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        self.assertTrue(data["whatsapp_url"].startswith("https://wa.me/221761234567?text="))
        self.assertIn("150 000 F CFA", data["message"])
        self.assertEqual(RentReminder.objects.get().sent_by, self.admin_a)
        self.assertIsNotNone(self.api_a.get(ROLL).json()["rows"][0]["last_reminder_at"])

    def test_nothing_due_means_no_reminder(self):
        self.assertEqual(self.api_a.post(self.URL, {"lease": self.lease.id}).status_code, 400)
        self.assertEqual(self.api_a.get(f"{self.URL}preview/{self.lease.id}/").status_code, 400)
        self.assertEqual(self.api_b.get(f"{self.URL}preview/{self.lease.id}/").status_code, 404)


class ReceiptTests(RentWorkTestCase):
    def test_receipt_only_once_settled(self):
        schedule = self.schedule(self.month)
        url = f"/api/v1/payments/schedules/{schedule.id}/receipt/"
        self.assertEqual(self.api_a.get(url).status_code, 400)
        payment = self.collect("150000").json()["payment"]
        response = self.api_a.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))
        receipt = self.api_a.get(f"/api/v1/payments/payments/{payment['id']}/receipt/")
        self.assertTrue(receipt.content.startswith(b"%PDF"))
        self.assertEqual(self.api_b.get(url).status_code, 404)

    def test_shared_link_opens_without_account_and_dies_with_the_payment(self):
        schedule = self.schedule(self.month)
        payment = self.collect("150000").json()["payment"]
        share = self.api_a.get(f"/api/v1/payments/schedules/{schedule.id}/receipt/share/").json()
        self.assertIn("wa.me/221761234567", share["whatsapp_url"])
        token = share["url"].rsplit("/", 1)[1]
        link = f"/api/v1/documents/{token}/"
        anonymous = self.client_class()
        self.assertEqual(anonymous.get(link).status_code, 200)
        self.assertEqual(anonymous.get(f"/api/v1/documents/{token[:-2]}xx/").status_code, 404)
        self.api_a.post(f"/api/v1/payments/payments/{payment['id']}/cancel/", {"reason": "Erreur"})
        self.assertEqual(anonymous.get(link).status_code, 404)

    def test_names_with_markup_do_not_break_the_document(self):
        self.org_a.name = "Agence <b> & Fils"
        self.org_a.save()
        schedule = self.schedule(self.month)
        self.collect("150000")
        self.assertEqual(self.api_a.get(f"/api/v1/payments/schedules/{schedule.id}/receipt/").status_code, 200)

    def test_period_of_a_schedule(self):
        self.lease.start_date = date(2026, 1, 15)
        self.lease.end_date = None
        schedule = make_schedule(self.lease)
        schedule.lease_contract = self.lease
        schedule.due_date = date(2026, 1, 15)
        self.assertEqual(schedule_period(schedule), (date(2026, 1, 15), date(2026, 1, 31)))
        schedule.due_date = date(2026, 3, 5)
        self.assertEqual(schedule_period(schedule), (date(2026, 3, 1), date(2026, 3, 31)))
        self.lease.payment_frequency = "QUARTERLY"
        schedule.due_date = date(2026, 4, 5)
        self.assertEqual(schedule_period(schedule), (date(2026, 4, 1), date(2026, 6, 30)))


class OwnerTests(RentWorkTestCase):
    def setUp(self):
        super().setUp()
        self.owner = make_owner(self.org_a)
        self.property = self.lease.unit.building.property
        Property.objects.filter(pk=self.property.pk).update(owner=self.owner, commission_rate=Decimal("10"))
        self.statement_url = f"/api/v1/owners/{self.owner.id}/statement/"

    def statement(self, month=None):
        month = month or self.month
        return self.api_a.get(f"{self.statement_url}?month={month:%Y-%m}").json()

    def test_statement_collects_commission_expenses_and_payouts(self):
        self.schedule(self.month)
        self.collect("150000")
        expense = self.api_a.post("/api/v1/owners/expenses/", {
            "property": self.property.id, "label": "Plomberie", "amount": "20000", "spent_on": self.month,
        })
        self.assertEqual(expense.status_code, 201, expense.content)
        payout = self.api_a.post("/api/v1/owners/payouts/", {"owner": self.owner.id, "amount": "100000", "paid_on": self.month})
        self.assertEqual(payout.status_code, 201, payout.content)
        data = self.statement()
        self.assertEqual(Decimal(data["collected"]), Decimal("150000"))
        self.assertEqual(Decimal(data["commission"]), Decimal("15000"))
        self.assertEqual(Decimal(data["net"]), Decimal("115000"))
        self.assertEqual(Decimal(data["closing_balance"]), Decimal("15000"))
        self.assertEqual(Decimal(self.api_a.get(f"/api/v1/owners/{self.owner.id}/").json()["balance"]), Decimal("15000"))
        # Un reversement annulé revient au solde.
        self.api_a.post(f"/api/v1/owners/payouts/{payout.json()['id']}/cancel/", {"reason": "Rejeté"})
        self.assertEqual(Decimal(self.statement()["closing_balance"]), Decimal("115000"))

    def test_balance_carries_over_and_rate_is_frozen(self):
        self.schedule(self.previous)
        self.collect("150000", payment_date=f"{self.previous:%Y-%m}-10T10:00:00Z")
        Property.objects.filter(pk=self.property.pk).update(commission_rate=Decimal("20"))
        previous = self.statement(self.previous)
        self.assertEqual(Decimal(previous["commission"]), Decimal("15000"))
        self.assertEqual(Decimal(self.statement()["opening_balance"]), Decimal("135000"))

    def test_deposit_is_not_owed_to_the_owner(self):
        self.schedule(self.month, "300000", kind="DEPOSIT")
        self.collect("300000")
        self.assertEqual(Decimal(self.statement()["closing_balance"]), 0)

    def test_pdf_and_share(self):
        self.schedule(self.month)
        self.collect("150000")
        pdf = self.api_a.get(f"{self.statement_url}pdf/")
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        token = self.api_a.get(f"{self.statement_url}share/").json()["url"].rsplit("/", 1)[1]
        self.assertEqual(self.client_class().get(f"/api/v1/documents/{token}/").status_code, 200)

    def test_isolation_and_rights(self):
        self.assertEqual(self.api_b.get(self.statement_url).status_code, 404)
        self.assertEqual(self.api_b.get("/api/v1/owners/").json()["results"], [])
        self.assertEqual(self.api_b.post("/api/v1/owners/payouts/", {"owner": self.owner.id, "amount": "1"}).status_code, 400)
        self.assertEqual(self.api_b.post("/api/v1/owners/expenses/", {"property": self.property.id, "label": "x", "amount": "1"}).status_code, 400)
        accountant = client_for(add_member(self.org_a, role="ACCOUNTANT"))
        self.assertEqual(accountant.post("/api/v1/owners/payouts/", {"owner": self.owner.id, "amount": "1"}).status_code, 201)
        self.assertEqual(accountant.post("/api/v1/owners/", {"phone": "770001122", "first_name": "A", "last_name": "B"}).status_code, 403)

    def test_expense_unit_must_be_in_the_property(self):
        response = self.api_a.post("/api/v1/owners/expenses/", {
            "property": self.property.id, "unit": make_unit(self.org_a).id, "label": "x", "amount": "1",
        })
        self.assertEqual(response.status_code, 400)

    def test_owner_registration(self):
        body = {"phone": "77 000 11 22", "first_name": "Mame", "last_name": "Fall"}
        created = self.api_a.post("/api/v1/owners/", body)
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.json()["phone"], "+221770001122")
        self.assertEqual(self.api_a.post("/api/v1/owners/", body).status_code, 400)
        self.assertEqual(self.api_b.post("/api/v1/owners/", body).status_code, 201)
