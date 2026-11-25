"""Offres, règlements d'abonnement, limites pendant l'essai, demandes d'offre."""

from datetime import date, timedelta
from decimal import Decimal

from django.core import mail
from django.test import override_settings
from django.utils import timezone

from mailing.daily import run_daily
from mailing.models import OutgoingEmail
from notifications.models import InAppNotification
from notifications.services import sync_platform_reminders, sync_reminders
from organizations.models import Organization
from subscriptions.billing import add_months
from subscriptions.models import BillingSettings, PlanRequest, Subscription, SubscriptionPayment, SubscriptionPlan

from .factories import DahooTestCase, add_member, client_for, make_unit, make_user, payment_method

PLANS = "/api/v1/platform/plans/"
PROPERTY = {"name": "Résidence", "address": "Rue 1", "city": "Dakar"}


class BillingCase(DahooTestCase):
    def setUp(self):
        super().setUp()
        self.platform = client_for(make_user(is_staff=True))
        self.method = payment_method()
        self.basic = SubscriptionPlan.objects.create(name="Basique", billing_type="MONTHLY", price=15000, max_units=20)
        self.pro = SubscriptionPlan.objects.create(name="Pro", billing_type="MONTHLY", price=45000)
        self.today = timezone.localdate()
        # Essai terminé depuis dix jours, sauf mention contraire.
        self.set_trial(-10)

    def set_trial(self, days, organization=None):
        organization = organization or self.org_a
        organization.trial_ends_at = timezone.now() + timedelta(days=days)
        organization.save(update_fields=["trial_ends_at"])

    def url(self, path, organization=None):
        return f"/api/v1/platform/organizations/{(organization or self.org_a).pk}/billing/{path}"

    def pay(self, plan=None, expect=201, **fields):
        body = {"plan": (plan or self.basic).pk, "method": "WAVE", **fields}
        response = self.platform.post(self.url("payments/"), body, format="json")
        self.assertEqual(response.status_code, expect, response.content)
        return response.json()

    def quote(self, plan=None, expect=200, **fields):
        response = self.platform.post(self.url("quote/"), {"plan": (plan or self.basic).pk, **fields}, format="json")
        self.assertEqual(response.status_code, expect, response.content)
        return response.json()

    def access(self):
        return self.api_a.get("/api/v1/organizations/current/").json()["access_status"]

    def subscription(self):
        return Subscription.objects.get(organization=self.org_a)


class AddMonthsTests(DahooTestCase):
    def test_end_of_month(self):
        self.assertEqual(add_months(date(2026, 1, 31), 1), date(2026, 2, 28))
        self.assertEqual(add_months(date(2026, 11, 25), 2), date(2027, 1, 25))
        self.assertEqual(add_months(date(2028, 2, 29), 12), date(2029, 2, 28))


class PlanTests(BillingCase):
    def test_reserved_to_dahoo_team(self):
        for path in (PLANS, "/api/v1/platform/billing/", "/api/v1/platform/billing/settings/", self.url(""), self.url("reminder/"), "/api/v1/platform/subscription-payments/"):
            self.assertEqual(self.api_a.get(path).status_code, 403, path)
        self.assertEqual(self.api_a.post(self.url("payments/"), {"plan": self.basic.pk, "method": "WAVE"}).status_code, 403)
        self.assertEqual(self.api_a.post(PLANS, {"name": "Gratuit", "billing_type": "MONTHLY", "price": 0}).status_code, 403)

    def test_create_and_publish(self):
        body = {"name": "Propriétaire", "description": "Jusqu'à 5 lots", "audience": "OWNER", "billing_type": "MONTHLY", "price": "5000", "max_units": 5}
        self.assertEqual(self.platform.post(PLANS, body, format="json").status_code, 201)
        public = next(p for p in self.client.get("/api/v1/public/plans/").json() if p["name"] == "Propriétaire")
        self.assertEqual((public["audience"], public["description"]), ("OWNER", "Jusqu'à 5 lots"))
        # Une agence ne se voit pas proposer une offre de propriétaire.
        names = [plan["name"] for plan in self.api_a.get("/api/v1/subscriptions/overview/").json()["plans"]]
        self.assertEqual(names, ["Basique", "Pro"])

    def test_price_and_rate_are_required(self):
        self.assertIn("price", self.platform.post(PLANS, {"name": "X", "billing_type": "MONTHLY"}, format="json").json())
        for rate in (None, 0, 120):
            response = self.platform.post(PLANS, {"name": "X", "billing_type": "COMMISSION", "commission_rate": rate}, format="json")
            self.assertIn("commission_rate", response.json())
        created = self.platform.post(PLANS, {"name": "X", "billing_type": "COMMISSION", "commission_rate": 2.5, "price": 9000}, format="json").json()
        self.assertIsNone(created["price"])

    def test_new_price_does_not_touch_subscribers(self):
        self.pay()
        self.platform.patch(f"{PLANS}{self.basic.pk}/", {"price": "20000"}, format="json")
        self.assertEqual(self.subscription().price, 15000)
        self.assertEqual(self.quote()["amount"], "15000.00")
        # Un nouveau client paie le nouveau prix.
        response = self.platform.post(self.url("quote/", self.org_b), {"plan": self.basic.pk}, format="json")
        self.assertEqual(response.json()["amount"], "20000.00")

    def test_subscribers_keep_their_limits(self):
        self.pay()
        path = f"{PLANS}{self.basic.pk}/"
        self.assertIn("max_units", self.platform.patch(path, {"max_units": 10}, format="json").json())
        self.assertIn("max_properties", self.platform.patch(path, {"max_properties": 5}, format="json").json())
        self.assertIn("billing_type", self.platform.patch(path, {"billing_type": "YEARLY"}, format="json").json())
        self.assertEqual(self.platform.patch(path, {"max_units": 30}, format="json").status_code, 200)
        self.assertEqual(self.platform.patch(path, {"max_units": None}, format="json").status_code, 200)

    def test_delete_only_unused(self):
        self.pay()
        response = self.platform.delete(f"{PLANS}{self.basic.pk}/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("retirez-la", response.json()["detail"])
        self.assertEqual(self.platform.delete(f"{PLANS}{self.pro.pk}/").status_code, 204)

    def test_withdrawn_plan_renews_but_does_not_sell(self):
        self.pay()
        SubscriptionPlan.objects.update(active=False)
        self.assertEqual(self.quote()["renews"], True)
        self.assertIn("plan", self.quote(self.pro, expect=400))

    def test_subscribers_count(self):
        self.pay()
        counts = {plan["name"]: plan["subscribers"] for plan in self.platform.get(PLANS).json()}
        self.assertEqual(counts, {"Basique": 1, "Pro": 0})


class TrialLimitTests(BillingCase):
    def setUp(self):
        super().setUp()
        self.set_trial(20)

    def test_only_one_plan_limits_the_trial(self):
        self.platform.patch(f"{PLANS}{self.basic.pk}/", {"limits_trial": True}, format="json")
        response = self.platform.patch(f"{PLANS}{self.pro.pk}/", {"limits_trial": True}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(list(SubscriptionPlan.objects.filter(limits_trial=True)), [self.pro])
        created = self.platform.post(PLANS, {"name": "Essai", "billing_type": "MONTHLY", "price": 0, "limits_trial": True}, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(SubscriptionPlan.objects.get(limits_trial=True).name, "Essai")

    def test_no_plan_means_unlimited_trial(self):
        self.assertEqual(self.api_a.post("/api/v1/properties/properties/", PROPERTY).status_code, 201)

    def test_trial_limit(self):
        SubscriptionPlan.objects.create(name="Découverte", billing_type="MONTHLY", price=0, max_properties=1, limits_trial=True, active=False)
        self.assertEqual(self.api_a.post("/api/v1/properties/properties/", PROPERTY).status_code, 201)
        response = self.api_a.post("/api/v1/properties/properties/", PROPERTY)
        self.assertEqual(response.status_code, 400)
        self.assertIn("essai", response.json()["detail"])
        # L'offre payée remplace les limites de l'essai, tout de suite.
        self.pay()
        self.assertEqual(self.api_a.post("/api/v1/properties/properties/", PROPERTY).status_code, 201)

    def test_internal_organization_is_not_limited(self):
        SubscriptionPlan.objects.create(name="Découverte", billing_type="MONTHLY", price=0, max_properties=0, limits_trial=True)
        dahoo = Organization.objects.create(name="Dahoo", is_internal=True)
        self.assertEqual(client_for(add_member(dahoo)).post("/api/v1/properties/properties/", PROPERTY).status_code, 201)

    def test_reactivating_a_member_counts(self):
        self.basic.max_users = 2
        self.basic.save()
        self.pay()
        first, second = add_member(self.org_a), add_member(self.org_a)
        membership = self.org_a.memberships.get(user=first)
        membership.is_active = False
        membership.save()
        response = self.api_a.patch(f"/api/v1/organizations/members/{membership.pk}/", {"is_active": True})
        self.assertEqual(response.status_code, 400, response.content)
        self.org_a.memberships.filter(user=second).update(is_active=False)
        self.assertEqual(self.api_a.patch(f"/api/v1/organizations/members/{membership.pk}/", {"is_active": True}).status_code, 200)


class PaymentTests(BillingCase):
    def test_first_payment_opens_access(self):
        self.assertEqual(self.access(), "EXPIRED")
        data = self.pay(reference="W-1")
        self.assertEqual(data["amount"], "15000.00")
        self.assertEqual(data["period_start"], self.today.isoformat())
        self.assertEqual(data["period_end"], (add_months(self.today, 1) - timedelta(days=1)).isoformat())
        self.assertEqual(self.access(), "ACTIVE")
        self.assertEqual(self.subscription().end_date.isoformat(), data["period_end"])
        me = self.api_a.get("/api/v1/users/me/").json()["memberships"][0]
        self.assertEqual(me["subscription_ends_on"], data["period_end"])

    def test_renewal_follows_the_paid_period(self):
        first = self.pay(quantity=2)
        second = self.pay(quantity=3)
        self.assertEqual(second["period_start"], (date.fromisoformat(first["period_end"]) + timedelta(days=1)).isoformat())
        self.assertEqual(Decimal(second["amount"]), 45000)
        self.assertEqual(self.subscription().end_date.isoformat(), second["period_end"])

    def test_late_renewal_restarts_on_payment_day(self):
        start = self.today - timedelta(days=90)
        subscription = Subscription.objects.create(organization=self.org_a, plan=self.basic, start_date=start, end_date=self.today - timedelta(days=20))
        paid_on = self.today - timedelta(days=2)
        data = self.pay(paid_on=paid_on.isoformat())
        self.assertEqual(data["period_start"], paid_on.isoformat())
        self.assertEqual(data["subscription"], subscription.pk)

    def test_payment_during_trial_keeps_free_days(self):
        self.set_trial(12)
        self.assertEqual(self.quote()["free_days"], 12)
        data = self.pay()
        ends = timezone.localdate(self.org_a.trial_ends_at)
        self.assertEqual(data["period_start"], ends.isoformat())
        self.assertEqual(self.access(), "ACTIVE")
        self.assertEqual(self.subscription().start_date, self.today)

    def test_open_ended_subscription_becomes_dated(self):
        Subscription.objects.create(organization=self.org_a, plan=self.basic, start_date=self.today - timedelta(days=200))
        data = self.pay()
        self.assertEqual(data["period_start"], self.today.isoformat())
        self.assertEqual(self.subscription().end_date.isoformat(), data["period_end"])
        self.platform.post(f"/api/v1/platform/subscription-payments/{data['id']}/cancel/", {"reason": "Erreur"})
        self.assertIsNone(self.subscription().end_date)

    def test_yearly(self):
        yearly = SubscriptionPlan.objects.create(name="Annuel", billing_type="YEARLY", price=150000)
        data = self.pay(yearly)
        self.assertEqual(data["period_end"], (add_months(self.today, 12) - timedelta(days=1)).isoformat())

    def test_discount(self):
        self.assertEqual(self.pay(quantity=12, discount="30000")["amount"], "150000.00")
        self.assertIn("discount", self.quote(discount="15001", expect=400))
        self.assertIn("discount", self.quote(discount="-1", expect=400))

    def test_commission_takes_the_received_amount(self):
        commission = SubscriptionPlan.objects.create(name="Commission", billing_type="COMMISSION", commission_rate=3)
        self.assertIn("amount", self.quote(commission, expect=400))
        self.assertEqual(self.pay(commission, amount="62000")["amount"], "62000.00")

    def test_negotiated_price(self):
        self.pay()
        self.platform.patch(f"/api/v1/platform/subscriptions/{self.subscription().pk}/", {"price": "12000"}, format="json")
        self.assertEqual(self.quote()["amount"], "12000.00")

    def test_upgrade_deducts_paid_days(self):
        self.pay()
        quote = self.quote(self.pro)
        # Payé ce matin : toute la période reste à courir.
        self.assertEqual((quote["credit"], quote["amount"], quote["replaces"]), ("15000.00", "30000.00", "Basique"))
        data = self.pay(self.pro)
        self.assertEqual(data["period_start"], self.today.isoformat())
        old, new = Subscription.objects.filter(organization=self.org_a).order_by("pk")
        self.assertEqual((old.status, new.plan), ("EXPIRED", self.pro))

    def test_partial_credit(self):
        start = self.today - timedelta(days=14)
        self.pay(paid_on=start.isoformat())
        length = (add_months(start, 1) - start).days
        expected = int(Decimal(15000) * (length - 14) / length)
        self.assertEqual(Decimal(self.quote(self.pro)["credit"]), expected)

    def test_downgrade_never_loses_money(self):
        self.pay(self.pro, quantity=6)
        self.assertIn("quantity", self.quote(self.basic, expect=400))
        self.assertEqual(Decimal(self.quote(self.basic, quantity=20)["amount"]), 300000 - 270000)

    def test_warns_when_usage_exceeds_the_plan(self):
        self.basic.max_units = 1
        self.basic.save()
        make_unit(self.org_a), make_unit(self.org_a)
        self.assertIn("2 déjà créés pour 1", self.quote()["warnings"][0])

    def test_guards(self):
        self.assertIn("paid_on", self.quote(paid_on=(self.today + timedelta(days=1)).isoformat(), expect=400))
        self.assertIn("paid_on", self.quote(paid_on=(self.today - timedelta(days=90)).isoformat(), expect=400))
        self.assertIn("quantity", self.quote(quantity=0, expect=400))
        self.pay(reference="W-1")
        self.assertIn("reference", self.pay(reference="w-1 ", expect=400))
        self.assertEqual(SubscriptionPayment.objects.count(), 1)
        dahoo = Organization.objects.create(name="Dahoo", is_internal=True)
        response = self.platform.post(self.url("payments/", dahoo), {"plan": self.basic.pk, "method": "WAVE"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_quote_writes_nothing(self):
        self.quote()
        self.assertFalse(Subscription.objects.exists())


class CancelTests(BillingCase):
    def cancel(self, payment, expect=200, reason="Saisi deux fois"):
        response = self.platform.post(f"/api/v1/platform/subscription-payments/{payment['id']}/cancel/", {"reason": reason})
        self.assertEqual(response.status_code, expect, response.content)
        return response.json()

    def test_cancel_opening_closes_access(self):
        payment = self.pay(reference="W-1")
        self.assertIsNotNone(self.cancel(payment)["cancelled_at"])
        self.assertEqual(self.access(), "EXPIRED")
        # La référence redevient libre, et l'agence peut régler de nouveau.
        self.pay(reference="W-1")
        self.assertEqual(self.access(), "ACTIVE")

    def test_cancel_renewal_restores_previous_end(self):
        first, second = self.pay(), self.pay()
        self.cancel(second)
        self.assertEqual(self.subscription().end_date.isoformat(), first["period_end"])

    def test_cancel_upgrade_restores_the_old_plan(self):
        first = self.pay()
        self.cancel(self.pay(self.pro))
        running = Subscription.objects.get(organization=self.org_a, status="ACTIVE")
        self.assertEqual((running.plan, running.end_date.isoformat()), (self.basic, first["period_end"]))
        # Le renouvellement suivant repart bien de l'ancienne offre.
        self.assertTrue(self.quote()["renews"])

    def test_only_the_latest(self):
        first, second = self.pay(), self.pay()
        self.assertIn("plus récent", self.cancel(first, expect=400)["detail"])
        self.cancel(second)
        self.assertIn("déjà annulé", self.cancel(second, expect=400)["detail"])
        self.cancel(first)

    def test_manual_end_is_not_overwritten(self):
        self.pay()
        payment = self.pay()
        subscription = self.subscription()
        subscription.end_date = self.today + timedelta(days=5)
        subscription.save()
        self.cancel(payment)
        self.assertEqual(self.subscription().end_date, self.today + timedelta(days=5))

    def test_reason_is_required(self):
        self.assertIn("reason", self.cancel(self.pay(), expect=400, reason=""))


class ReceiptTests(BillingCase):
    def test_client_downloads_its_own_receipt(self):
        payment = self.pay()
        path = f"/api/v1/subscriptions/payments/{payment['id']}/receipt/"
        response = self.api_a.get(path)
        self.assertEqual((response.status_code, response["Content-Type"]), (200, "application/pdf"))
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertEqual(self.api_b.get(path).status_code, 404)
        self.assertEqual(self.platform.get(f"/api/v1/platform/subscription-payments/{payment['id']}/receipt/").status_code, 200)
        self.assertEqual(len(self.api_a.get("/api/v1/subscriptions/payments/").json()["results"]), 1)
        self.assertEqual(len(self.api_b.get("/api/v1/subscriptions/payments/").json()["results"]), 0)

    def test_receipt_with_credit_discount_and_odd_text(self):
        BillingSettings.objects.update_or_create(pk=1, defaults={"legal_notice": "NINEA <à compléter> & RC"})
        self.org_a.name = "Keur & <Fils>"
        self.org_a.save()
        self.pay()
        payment = self.pay(self.pro, discount="1000")
        self.assertEqual(self.api_a.get(f"/api/v1/subscriptions/payments/{payment['id']}/receipt/").status_code, 200)

    def test_shared_link_dies_when_cancelled(self):
        from documents.receipts import share_url

        payment = self.pay()
        token = share_url("subscription", payment["id"]).rsplit("/", 1)[1]
        path = f"/api/v1/documents/{token}/"
        self.assertEqual(self.client.get(path).status_code, 200)
        self.platform.post(f"/api/v1/platform/subscription-payments/{payment['id']}/cancel/", {"reason": "Erreur"})
        self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(self.api_a.get("/api/v1/subscriptions/payments/").json()["count"], 0)


class OverviewTests(BillingCase):
    def test_client_overview(self):
        BillingSettings.objects.update_or_create(pk=1, defaults={"payment_instructions": "Wave, au nom de l'agence"})
        make_unit(self.org_a)
        data = self.api_a.get("/api/v1/subscriptions/overview/").json()
        self.assertEqual((data["state"], data["subscription"]), ("TRIAL_ENDED", None))
        self.assertEqual(data["payment_instructions"], "Wave, au nom de l'agence")
        self.pay()
        data = self.api_a.get("/api/v1/subscriptions/overview/").json()
        self.assertEqual((data["state"], data["subscription"]["plan"]["name"]), ("ACTIVE", "Basique"))
        usage = {row["resource"]: (row["used"], row["limit"]) for row in data["usage"]}
        self.assertEqual(usage, {"property": (1, None), "unit": (1, 20), "member": (1, None)})

    def test_states(self):
        subscription = Subscription.objects.create(
            organization=self.org_a, plan=self.basic, start_date=self.today - timedelta(days=30), end_date=self.today + timedelta(days=3)
        )
        state = lambda: self.platform.get(self.url("")).json()["state"]  # noqa: E731
        self.assertEqual(state(), "ENDING")
        Subscription.objects.filter(pk=subscription.pk).update(end_date=self.today - timedelta(days=1))
        self.assertEqual(state(), "LAPSED")
        self.set_trial(5)
        self.assertEqual(state(), "TRIAL")
        self.org_a.is_active = False
        self.org_a.save()
        self.assertEqual(state(), "SUSPENDED")

    def test_board(self):
        Organization.objects.create(name="Dahoo", is_internal=True)
        self.pay(quantity=2)
        cancelled = self.pay()
        self.platform.post(f"/api/v1/platform/subscription-payments/{cancelled['id']}/cancel/", {"reason": "Erreur"})
        data = self.platform.get("/api/v1/platform/billing/").json()
        self.assertEqual((data["mrr"], data["collected_month"]), ("15000.00", "30000.00"))
        self.assertEqual((data["subscribers"], data["trials"], data["to_renew"]), (1, 1, 0))
        self.assertEqual([row["organization"]["name"] for row in data["rows"]], ["Agence B", "Agence A"])
        self.assertEqual(self.platform.get("/api/v1/platform/dashboard/").json()["subscriptions"]["mrr"], "15000.00")

    def test_journal_filters(self):
        self.pay()
        path = "/api/v1/platform/subscription-payments/"
        self.assertEqual(self.platform.get(f"{path}?subscription__organization={self.org_a.pk}").json()["count"], 1)
        self.assertEqual(self.platform.get(f"{path}?subscription__organization={self.org_b.pk}").json()["count"], 0)

    def test_reminder_message(self):
        self.org_a.phone = "+221770000001"
        self.org_a.save()
        BillingSettings.objects.update_or_create(pk=1, defaults={"payment_instructions": "Wave au 77 000 00 00"})
        data = self.platform.get(self.url("reminder/")).json()
        self.assertIn("essai Dahoo s'est terminé", data["message"])
        self.assertIn("Wave au 77 000 00 00", data["message"])
        self.assertTrue(data["whatsapp_url"].startswith("https://wa.me/221770000001?text="))
        # Une ligne fixe ne reçoit pas WhatsApp : le message part vers l'administrateur.
        self.org_a.phone = "+221338000000"
        self.org_a.save()
        self.assertEqual(self.platform.get(self.url("reminder/")).json()["phone"], self.admin_a.phone)
        self.pay()
        self.assertIn("offre Basique (15 000 F CFA par mois), se termine le", self.platform.get(self.url("reminder/")).json()["message"])
        Subscription.objects.update(end_date=None)
        self.assertEqual(self.platform.get(self.url("reminder/")).status_code, 400)

    def test_settings(self):
        path = "/api/v1/platform/billing/settings/"
        self.assertEqual(self.platform.get(path).json(), {"payment_instructions": "", "legal_notice": ""})
        self.platform.patch(path, {"payment_instructions": "Wave"}, format="json")
        self.assertEqual(self.platform.get(path).json()["payment_instructions"], "Wave")


class PlanRequestTests(BillingCase):
    URL = "/api/v1/subscriptions/requests/"

    def test_request_in_read_only_then_payment_closes_it(self):
        self.assertEqual(self.access(), "EXPIRED")
        response = self.api_a.post(self.URL, {"plan": self.basic.pk, "message": "Nous avons 12 lots"})
        self.assertEqual(response.status_code, 201, response.content)
        row = self.platform.get("/api/v1/platform/billing/").json()["rows"][0]
        self.assertEqual((row["organization"]["name"], row["request"]["plan_name"]), ("Agence A", "Basique"))
        self.assertTrue(InAppNotification.objects.filter(kind="PLAN_REQUEST").exists())
        self.pay()
        self.assertEqual(PlanRequest.objects.get().status, "HANDLED")

    def test_new_request_replaces_the_previous(self):
        self.api_a.post(self.URL, {"plan": self.basic.pk})
        self.api_a.post(self.URL, {"plan": self.pro.pk})
        self.assertEqual(PlanRequest.objects.get().plan, self.pro)

    def test_rights_and_catalogue(self):
        viewer = client_for(add_member(self.org_a, role="VIEWER"))
        self.assertEqual(viewer.post(self.URL, {"plan": self.basic.pk}).status_code, 403)
        owner_plan = SubscriptionPlan.objects.create(name="P", audience="OWNER", billing_type="MONTHLY", price=1)
        self.assertEqual(self.api_a.post(self.URL, {"plan": owner_plan.pk}).status_code, 400)
        hidden = SubscriptionPlan.objects.create(name="H", active=False, billing_type="MONTHLY", price=1)
        self.assertEqual(self.api_a.post(self.URL, {"plan": hidden.pk}).status_code, 400)

    def test_handle_without_payment(self):
        self.api_a.post(self.URL, {"plan": self.basic.pk})
        path = f"/api/v1/platform/plan-requests/{PlanRequest.objects.get().pk}/handle/"
        self.assertEqual(self.api_a.post(path).status_code, 403)
        self.assertEqual(self.platform.post(path).json()["status"], "HANDLED")


@override_settings(EMAIL_SEND_IN_BACKGROUND=False)
class BillingEmailTests(BillingCase):
    def setUp(self):
        super().setUp()
        self.admin_a.email, self.admin_a.email_verified_at = "awa@teranga.sn", timezone.now()
        self.admin_a.save()

    def templates(self):
        return list(OutgoingEmail.objects.order_by("pk").values_list("template", flat=True))

    def test_receipt_after_payment(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.pay()
        self.assertEqual(self.templates(), ["subscription_receipt"])
        self.assertIn("réglé jusqu'au", mail.outbox[0].subject)

    def test_reminders_before_and_after_the_end(self):
        subscription = Subscription.objects.create(
            organization=self.org_a, plan=self.basic, start_date=self.today - timedelta(days=30), end_date=self.today + timedelta(days=7)
        )
        run_daily(self.org_a)
        run_daily(self.org_a)
        self.assertEqual(self.templates(), ["subscription_ending"])
        Subscription.objects.filter(pk=subscription.pk).update(end_date=self.today - timedelta(days=1))
        run_daily(self.org_a)
        run_daily(self.org_a)
        self.assertEqual(self.templates(), ["subscription_ending", "subscription_ended"])

    def test_no_reminder_without_end_date(self):
        Subscription.objects.create(organization=self.org_a, plan=self.basic, start_date=self.today)
        run_daily(self.org_a)
        self.assertEqual(self.templates(), [])

    def test_in_app_reminders(self):
        Subscription.objects.create(
            organization=self.org_a, plan=self.basic, start_date=self.today - timedelta(days=30), end_date=self.today + timedelta(days=2)
        )
        for _ in range(2):
            sync_reminders(self.org_a, force=True)
            sync_platform_reminders(force=True)
        self.assertEqual(InAppNotification.objects.filter(kind="SUBSCRIPTION_ENDING", user=self.admin_a).count(), 1)
        self.assertEqual(InAppNotification.objects.filter(kind="SUBSCRIPTION_ENDING").count(), 2)

    def test_request_reaches_the_team(self):
        make_user(is_staff=True, email="equipe@dahoo.sn", email_verified_at=timezone.now())
        self.api_a.post(PlanRequestTests.URL, {"plan": self.basic.pk})
        self.assertEqual(self.templates(), ["plan_request"])
