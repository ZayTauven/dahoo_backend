from decimal import Decimal

from payments.models import Payment

from .factories import DahooTestCase, make_lease, make_schedule, make_user, payment_method

PAYMENTS_URL = "/api/v1/payments/payments/"


class PaymentTests(DahooTestCase):
    def setUp(self):
        super().setUp()
        self.lease = make_lease(self.org_a, status="ACTIVE")
        self.schedule = make_schedule(self.lease, amount="150000")
        self.method = payment_method()

    def pay(self, amount, allocations=(), payer=None):
        return self.api_a.post(
            PAYMENTS_URL,
            {
                "payer": (payer or self.lease.tenant).id,
                "amount_paid": amount,
                "payment_method": self.method.id,
                "allocations": list(allocations),
            },
            format="json",
        )

    def test_schedule_list_works(self):
        # Régression : NameError `models` non importé -> 500.
        self.assertEqual(self.api_a.get("/api/v1/payments/schedules/").status_code, 200)

    def test_record_payment_with_full_allocation(self):
        response = self.pay("150000", [{"schedule": self.schedule.id, "amount": "150000"}])
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["recorded_by"], self.admin_a.id)
        self.schedule.refresh_from_db()
        self.assertTrue(self.schedule.is_paid)

    def test_partial_payments_accumulate(self):
        self.pay("100000", [{"schedule": self.schedule.id, "amount": "100000"}])
        self.schedule.refresh_from_db()
        self.assertFalse(self.schedule.is_paid)
        payment = self.pay("50000").json()
        response = self.api_a.post(
            f"{PAYMENTS_URL}{payment['id']}/allocate/",
            {"allocations": [{"schedule": self.schedule.id, "amount": "50000"}]},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.schedule.refresh_from_db()
        self.assertTrue(self.schedule.is_paid)

    def test_cannot_allocate_more_than_paid_and_nothing_is_saved(self):
        response = self.pay("1000", [{"schedule": self.schedule.id, "amount": "2000"}])
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Payment.objects.exists())

    def test_cannot_allocate_more_than_remaining_due(self):
        response = self.pay("200000", [{"schedule": self.schedule.id, "amount": "150000.01"}])
        self.assertEqual(response.status_code, 400)

    def test_duplicate_schedule_is_rejected(self):
        allocations = [{"schedule": self.schedule.id, "amount": "10"}] * 2
        self.assertEqual(self.pay("20", allocations).status_code, 400)

    def test_payer_must_be_a_tenant_of_the_organization(self):
        response = self.pay("10", payer=make_user())
        self.assertEqual(response.status_code, 400)
        self.assertIn("payer", response.json())

    def test_amount_must_be_positive(self):
        self.assertEqual(self.pay("0").status_code, 400)

    def test_schedule_needs_exactly_one_contract(self):
        response = self.api_a.post(
            "/api/v1/payments/schedules/",
            {"schedule_type": "RENT", "due_date": "2026-03-01", "amount_due": "10"},
        )
        self.assertEqual(response.status_code, 400)

    def test_amounts_are_exact_decimals(self):
        schedule = make_schedule(self.lease, amount="0.30")
        for _ in range(3):
            self.pay("0.10", [{"schedule": schedule.id, "amount": "0.10"}])
        schedule.refresh_from_db()
        self.assertTrue(schedule.is_paid)
        self.assertEqual(sum(a.allocated_amount for a in schedule.allocations.all()), Decimal("0.30"))
