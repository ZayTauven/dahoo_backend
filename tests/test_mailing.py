"""E-mails : gabarits, file d'envoi, comptes, envois de l'agence, point du jour."""

import re
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core import mail
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from leases.models import LeaseContract, Tenant
from mailing.addresses import is_deliverable
from mailing.catalog import CATALOG
from mailing.daily import run_daily
from mailing.models import EmailOptOut, OutgoingEmail
from mailing.queue import deliver, queue_email
from mailing.render import build_message, opt_out_token
from mailing.samples import SAMPLES
from maintenance.models import MaintenanceAssignment, MaintenanceTicket
from notifications.signals import muted
from organizations.models import Membership, Organization
from payments.models import PaymentSchedule, RentReminder
from public.models import DemoRequest
from users.models import User

from .factories import (
    PASSWORD, DahooTestCase, add_member, client_for, make_lease, make_owner, make_tenant, make_unit, make_user, payment_method,
)

NEW = "Nouveau!Passe2027"


@override_settings(
    EMAIL_SEND_IN_BACKGROUND=False, EMAIL_ENABLED=True, EMAIL_TEST_RECIPIENT="", EMAIL_BLOCKED_DOMAINS={"bloque.sn"},
    PUBLIC_SITE_URL="https://dahoo.test-site.sn", DEFAULT_FROM_EMAIL="Dahoo <no-reply@dahoo.sn>",
)
class MailTestCase(DahooTestCase):
    def run_commits(self):
        return self.captureOnCommitCallbacks(execute=True)

    def subjects(self):
        return [message.subject for message in mail.outbox]

    def verify(self, user, email="awa@teranga.sn"):
        User.objects.filter(pk=user.pk).update(email=email, email_verified_at=timezone.now())
        user.refresh_from_db()
        return user


class TemplateTests(MailTestCase):
    def test_every_template_renders(self):
        self.assertEqual(set(CATALOG), set(SAMPLES))
        for code, spec in CATALOG.items():
            with self.subTest(code=code):
                organization = self.org_a if spec.on_behalf else None
                message = build_message(OutgoingEmail(to="a@b.sn", template=code, context=SAMPLES[code], organization=organization))
                html = message.alternatives[0][0]
                for text in (html, message.body, message.subject):
                    self.assertNotRegex(text, r"\{\{|\{%|\{[a-z]+\}", "variable non remplacée")
                self.assertNotIn("display:none", message.body)
                self.assertEqual(html.count("cid:illustration"), 1)
                self.assertEqual(len(message.attachments), 2)
                self.assertIn("Agence A" if spec.on_behalf else "Dahoo", html)

    def test_values_are_escaped(self):
        context = {**SAMPLES["rent_due"], "name": "<script>alert(1)</script>"}
        html = build_message(OutgoingEmail(to="a@b.sn", template="rent_due", context=context, organization=self.org_a)).alternatives[0][0]
        self.assertNotIn("<script>alert", html)

    def test_sender_is_the_agency(self):
        Organization.objects.filter(pk=self.org_a.pk).update(name="Agence\nTeranga", email="contact@teranga.sn")
        self.org_a.refresh_from_db()
        message = build_message(OutgoingEmail(to="a@b.sn", template="rent_due", context=SAMPLES["rent_due"], organization=self.org_a))
        self.assertEqual(message.from_email, "Agence Teranga via Dahoo <no-reply@dahoo.sn>")
        self.assertEqual(message.reply_to, ["contact@teranga.sn"])
        self.assertIn("/desinscription/", message.extra_headers["List-Unsubscribe"])
        message.message()  # en-têtes valides


class QueueTests(MailTestCase):
    def test_addresses(self):
        for address in ("a@gmail.com", "a@mail.teranga.sn"):
            self.assertTrue(is_deliverable(address), address)
        for address in ("", None, "a", "a@localhost", "a@example.com", "a@x.test", "a@bloque.sn", "a@mail.bloque.sn"):
            self.assertFalse(is_deliverable(address), address)

    def test_sent_after_commit_only(self):
        with self.run_commits():
            queue_email("email_confirm", "a@gmail.com", SAMPLES["email_confirm"])
            self.assertEqual(mail.outbox, [])
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(OutgoingEmail.objects.get().status, "SENT")

    def test_smtp_failure_is_kept_and_retried(self):
        with patch("mailing.queue.build_message", side_effect=OSError("SMTP injoignable")), self.run_commits():
            queue_email("email_confirm", "a@gmail.com", SAMPLES["email_confirm"])
        email = OutgoingEmail.objects.get()
        self.assertEqual((email.status, email.attempts), ("PENDING", 1))
        self.assertIn("SMTP injoignable", email.error)
        self.assertEqual(deliver(), (1, 0))
        with patch("mailing.queue.build_message", side_effect=OSError("x")):
            OutgoingEmail.objects.update(status="PENDING", attempts=4)
            deliver()
        self.assertEqual(OutgoingEmail.objects.get().status, "FAILED")

    def test_same_key_is_sent_once(self):
        with self.run_commits():
            for _ in range(2):
                queue_email("rent_due", "a@gmail.com", SAMPLES["rent_due"], organization=self.org_a, dedupe_key="due:1")
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(EMAIL_ENABLED=False)
    def test_kill_switch(self):
        with self.run_commits():
            queue_email("email_confirm", "a@gmail.com", SAMPLES["email_confirm"])
        self.assertEqual(mail.outbox, [])
        self.assertEqual(OutgoingEmail.objects.get().status, "SKIPPED")

    @override_settings(EMAIL_TEST_RECIPIENT="recette@dahoo.sn")
    def test_test_recipient_replaces_everyone(self):
        with self.run_commits():
            queue_email("email_confirm", "a@gmail.com", SAMPLES["email_confirm"])
        self.assertEqual(mail.outbox[0].to, ["recette@dahoo.sn"])
        self.assertIn("[a@gmail.com]", mail.outbox[0].subject)

    def test_opt_out_stops_reminders_not_receipts(self):
        api = self.client_class()
        token = opt_out_token(self.org_a.pk, "A@gmail.com")
        self.assertEqual(api.post("/api/v1/emails/opt-out/", {"token": token}).json(), {"organization": "Agence A"})
        self.assertEqual(api.post("/api/v1/emails/opt-out/", {"token": token + "x"}).status_code, 400)
        self.assertEqual(EmailOptOut.objects.get().email, "a@gmail.com")
        with self.run_commits():
            self.assertIsNone(queue_email("rent_due", "a@gmail.com", SAMPLES["rent_due"], organization=self.org_a))
            self.assertIsNotNone(queue_email("rent_due", "a@gmail.com", SAMPLES["rent_due"], organization=self.org_b))
            self.assertIsNotNone(queue_email("rent_receipt", "a@gmail.com", SAMPLES["rent_receipt"], organization=self.org_a))

    def test_test_command(self):
        call_command("send_test_emails", "recette@gmail.com", verbosity=0)
        self.assertEqual(len(mail.outbox), len(CATALOG))


class AccountTests(MailTestCase):
    def link(self, message, name):
        return re.search(rf"/{name}/?([^\s]*)", message.body)[1]

    def test_forgotten_password(self):
        self.verify(self.admin_a)
        api = self.client_class()
        login = api.post("/api/v1/users/login/", {"phone": self.admin_a.phone, "password": PASSWORD}).json()
        with self.run_commits():
            self.assertEqual(api.post("/api/v1/users/password/forgot/", {"phone": self.admin_a.phone}).status_code, 204)
        uid, token = re.search(r"id=([^&\s]+)&jeton=(\S+)", mail.outbox[0].body).groups()
        body = {"uid": uid, "token": token, "new_password": NEW}
        self.assertEqual(api.post("/api/v1/users/password/reset/", {**body, "new_password": "123"}).status_code, 400)
        with self.run_commits():
            self.assertEqual(api.post("/api/v1/users/password/reset/", body).status_code, 204)
        # Le lien ne sert qu'une fois, les anciennes sessions sont fermées, la personne est prévenue.
        self.assertEqual(api.post("/api/v1/users/password/reset/", body).status_code, 400)
        self.assertEqual(api.post("/api/v1/users/refresh/", {"refresh": login["refresh"]}).status_code, 401)
        self.assertEqual(api.post("/api/v1/users/login/", {"phone": self.admin_a.phone, "password": NEW}).status_code, 200)
        self.assertEqual(self.subjects()[-1], "Votre mot de passe a été modifié")

    def test_forgotten_password_reveals_nothing(self):
        unverified = make_user(email="typo@gmail.com")
        tenant = make_tenant(self.org_a)
        self.verify(tenant, "locataire@gmail.com")
        with self.run_commits():
            for phone in ("+221709999999", unverified.phone, tenant.phone):
                response = self.client_class().post("/api/v1/users/password/forgot/", {"phone": phone})
                self.assertEqual((response.status_code, response.content), (204, b""))
        self.assertEqual(mail.outbox, [])

    def test_forgotten_password_is_not_a_flood(self):
        self.verify(self.admin_a)
        with self.run_commits():
            for _ in range(3):
                self.client_class().post("/api/v1/users/password/forgot/", {"phone": self.admin_a.phone})
        self.assertEqual(len(mail.outbox), 1)

    def test_forged_reset_is_refused(self):
        for uid, token in (("xx", "yy"), ("MQ", "bad-token"), ("", "")):
            response = self.client_class().post("/api/v1/users/password/reset/", {"uid": uid, "token": token, "new_password": NEW})
            self.assertEqual(response.status_code, 400)

    def test_email_is_saved_once_confirmed(self):
        url = "/api/v1/users/me/email/"
        self.assertEqual(self.api_a.post(url, {"email": "awa@gmail.com", "current_password": "faux"}).status_code, 400)
        self.assertEqual(self.api_a.post(url, {"email": "awa@example.com", "current_password": PASSWORD}).status_code, 400)
        with self.run_commits():
            self.assertEqual(self.api_a.post(url, {"email": "Awa@gmail.com", "current_password": PASSWORD}).status_code, 204)
        self.assertEqual(self.api_a.get("/api/v1/users/me/").json()["email_verified"], False)
        token = self.link(mail.outbox[0], "confirmer-email")
        api = self.client_class()
        self.assertEqual(api.post("/api/v1/users/email/confirm/", {"token": token + "x"}).status_code, 400)
        self.assertEqual(api.post("/api/v1/users/email/confirm/", {"token": token}).status_code, 204)
        self.admin_a.refresh_from_db()
        me = self.api_a.get("/api/v1/users/me/").json()
        self.assertEqual((me["email"], me["email_verified"]), ("awa@gmail.com", True))

    def test_preferences_only(self):
        response = self.api_a.patch("/api/v1/users/me/", {"email_digest": False, "email": "pirate@gmail.com", "phone": "+221700000000"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.admin_a.refresh_from_db()
        self.assertFalse(self.admin_a.email_digest)
        self.assertNotEqual(self.admin_a.email, "pirate@gmail.com")

    def test_new_member_is_welcomed(self):
        with self.run_commits():
            response = self.api_a.post("/api/v1/organizations/members/", {
                "phone": "77 111 22 33", "first_name": "Binta", "last_name": "Sy", "password": NEW, "email": "binta@gmail.com", "role": "MANAGER",
            })
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(self.subjects(), ["Bienvenue sur Dahoo"])
        self.assertNotIn(NEW, mail.outbox[0].body)

    def test_temporary_password_is_never_in_the_message(self):
        member = self.verify(add_member(self.org_a, role="MANAGER"), "m@gmail.com")
        membership = Membership.objects.get(user=member)
        with self.run_commits():
            password = self.api_a.post(f"/api/v1/organizations/members/{membership.id}/reset-password/").json()["temporary_password"]
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn(password, mail.outbox[0].body + mail.outbox[0].alternatives[0][0])
        self.assertFalse(OutgoingEmail.objects.filter(context__icontains=password).exists())


class AgencyMailCase(MailTestCase):
    def setUp(self):
        super().setUp()
        self.tenant = make_tenant(self.org_a, first_name="Awa", last_name="Sow")
        Tenant.objects.filter(user=self.tenant).update(email="locataire@gmail.com")
        self.lease = make_lease(self.org_a, status="ACTIVE", tenant=self.tenant, unit=make_unit(self.org_a, status="RENTED"))
        self.today = timezone.localdate()

    def option(self, **fields):
        Organization.objects.filter(pk=self.org_a.pk).update(**fields)
        self.org_a.refresh_from_db()

    def schedule(self, days, amount="150000"):
        return PaymentSchedule.objects.create(
            organization=self.org_a, lease_contract=self.lease, schedule_type="RENT",
            due_date=self.today + timedelta(days=days), amount_due=Decimal(amount),
        )

    def collect(self, amount="150000"):
        with self.run_commits():
            return self.api_a.post(
                "/api/v1/payments/collect/", {"lease": self.lease.id, "amount": amount, "payment_method": payment_method().id}, format="json"
            ).json()["payment"]["id"]


class AgencyTests(AgencyMailCase):
    def test_nothing_leaves_without_the_agencys_consent(self):
        self.schedule(-10)
        self.collect("1000")
        with self.run_commits():
            run_daily(self.org_a, today=self.today)
        self.assertEqual(mail.outbox, [])

    def test_automatic_receipt(self):
        self.option(email_receipts=True)
        self.schedule(-1)
        self.collect("50000")
        self.collect("100000")
        self.assertEqual(self.subjects()[0], "Nous avons bien reçu votre paiement")
        self.assertTrue(self.subjects()[1].startswith("Votre quittance de loyer"))
        self.assertIn("https://dahoo.test-site.sn/d/", mail.outbox[1].body)
        self.assertEqual(mail.outbox[0].to, ["locataire@gmail.com"])

    def test_the_address_of_another_agency_is_never_used(self):
        self.option(email_receipts=True)
        Tenant.objects.filter(user=self.tenant).update(email="")
        User.objects.filter(pk=self.tenant.pk).update(email="autre@gmail.com")
        self.schedule(-1)
        self.collect()
        self.assertEqual(mail.outbox, [])

    def test_manual_receipt(self):
        payment = None
        schedule = self.schedule(-1)
        payment = self.collect()
        with self.run_commits():
            self.assertEqual(self.api_a.post(f"/api/v1/payments/payments/{payment}/receipt/email/").status_code, 204)
            self.assertEqual(self.api_a.post(f"/api/v1/payments/schedules/{schedule.id}/receipt/email/").status_code, 204)
        self.assertEqual(len(mail.outbox), 2)
        Tenant.objects.filter(user=self.tenant).update(email="")
        self.assertEqual(self.api_a.post(f"/api/v1/payments/payments/{payment}/receipt/email/").status_code, 400)
        self.assertEqual(self.api_b.post(f"/api/v1/payments/payments/{payment}/receipt/email/").status_code, 404)
        viewer = client_for(add_member(self.org_a, role="VIEWER"))
        self.assertEqual(viewer.post(f"/api/v1/payments/payments/{payment}/receipt/email/").status_code, 403)

    def test_manual_reminder_by_email(self):
        self.schedule(-10)
        with self.run_commits():
            response = self.api_a.post("/api/v1/payments/reminders/", {"lease": self.lease.id, "channel": "EMAIL"})
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(self.subjects(), ["Un loyer reste à régler"])
        Tenant.objects.filter(user=self.tenant).update(email="")
        self.assertEqual(self.api_a.post("/api/v1/payments/reminders/", {"lease": self.lease.id, "channel": "EMAIL"}).status_code, 400)
        self.assertEqual(RentReminder.objects.count(), 1)

    def test_rent_roll_tells_who_can_be_emailed(self):
        self.schedule(-1)
        row = self.api_a.get("/api/v1/payments/rent-roll/").json()["rows"][0]
        self.assertEqual(row["tenant_email"], "locataire@gmail.com")

    def test_owner_statement_and_payout(self):
        owner = make_owner(self.org_a)
        owner.email = "bailleur@gmail.com"
        owner.save()
        with self.run_commits():
            self.assertEqual(self.api_a.post(f"/api/v1/owners/{owner.id}/statement/email/?month=2026-11").status_code, 204)
            self.api_a.post("/api/v1/owners/payouts/", {"owner": owner.id, "amount": "1000"})
        self.assertEqual(self.subjects(), ["Votre relevé de gestion, novembre 2026"])
        self.option(email_owner_payouts=True)
        with self.run_commits():
            self.api_a.post("/api/v1/owners/payouts/", {"owner": owner.id, "amount": "2000"})
        self.assertEqual(self.subjects()[-1], "Un reversement vous a été adressé")
        self.assertEqual(self.api_b.post(f"/api/v1/owners/{owner.id}/statement/email/").status_code, 404)


class DailyTests(AgencyMailCase):
    def daily(self, shift=0):
        with self.run_commits():
            run_daily(self.org_a, today=self.today + timedelta(days=shift))

    def test_due_reminder_once(self):
        self.option(email_due_reminders=True)
        self.schedule(3)
        self.schedule(20)
        self.daily()
        self.daily(1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(self.subjects()[0].startswith("Votre loyer est à régler le"))

    def test_overdue_at_5_then_15_days(self):
        self.option(email_overdue_reminders=True)
        self.schedule(-4)
        sent = []
        for shift in range(0, 14):
            self.daily(shift)
            sent.append(len(mail.outbox))
        self.assertEqual(sent, [0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2])
        self.assertEqual(RentReminder.objects.filter(channel="EMAIL", sent_by=None).count(), 2)
        reminders = self.api_a.get("/api/v1/payments/reminders/").json()["results"]
        self.assertEqual(reminders[0]["sent_by_name"], "Envoi automatique")

    def test_old_debts_do_not_trigger_a_burst(self):
        self.option(email_overdue_reminders=True)
        for days in (-200, -120, -60, -12, -8):
            self.schedule(days)
        self.daily()
        self.assertEqual(len(mail.outbox), 1)

    def test_expired_agency_sends_nothing(self):
        self.option(email_due_reminders=True, trial_ends_at=timezone.now() - timedelta(days=1))
        self.schedule(2)
        self.verify(self.admin_a)
        self.daily()
        self.assertEqual(mail.outbox, [])

    def test_digest_for_confirmed_members_only(self):
        self.schedule(-10)
        manager = self.verify(add_member(self.org_a, role="MANAGER"), "manager@gmail.com")
        add_member(self.org_a, user=make_user(email="non-confirme@gmail.com"))
        refused = self.verify(add_member(self.org_a), "refuse@gmail.com")
        User.objects.filter(pk=refused.pk).update(email_digest=False)
        self.daily()
        self.daily()
        self.assertEqual([message.to for message in mail.outbox], [["manager@gmail.com"]])
        self.assertIn("Awa Sow", mail.outbox[0].body)
        self.assertIsNotNone(manager)

    def test_no_digest_without_news(self):
        self.verify(self.admin_a)
        self.daily()
        self.assertEqual(mail.outbox, [])

    def test_digest_never_mixes_agencies(self):
        self.schedule(-10)
        user = self.verify(add_member(self.org_b), "double@gmail.com")
        add_member(self.org_a, user=user)
        with self.run_commits():
            run_daily(self.org_b, today=self.today)
        self.assertEqual(mail.outbox, [])
        self.daily()
        self.assertEqual(self.subjects(), ["Votre point du jour, Agence A"])

    def test_trial_ending(self):
        self.verify(self.admin_a)
        self.option(trial_ends_at=timezone.now() + timedelta(days=7))
        self.daily()
        self.assertTrue(any(subject.startswith("Votre essai se termine") for subject in self.subjects()))

    def test_command(self):
        self.option(email_due_reminders=True)
        self.schedule(2)
        with self.run_commits():
            call_command("sync_notifications", verbosity=0)
        self.assertEqual(len(mail.outbox), 1)


class TeamTests(AgencyMailCase):
    def test_tickets(self):
        manager = self.verify(add_member(self.org_a, role="MANAGER"), "manager@gmail.com")
        with self.run_commits():
            urgent = MaintenanceTicket.objects.create(unit=self.lease.unit, reported_by=self.admin_a, description="Fuite", priority="URGENT")
            MaintenanceTicket.objects.create(unit=self.lease.unit, reported_by=self.admin_a, description="Peinture", priority="LOW")
            MaintenanceAssignment.objects.create(ticket=urgent, assigned_to=manager, assigned_by=self.admin_a)
        self.assertEqual(sorted(subject.split(" :")[0] for subject in self.subjects()), ["Nouvelle panne", "Une intervention vous est confiée"])
        User.objects.filter(pk=manager.pk).update(email_alerts=False)
        with self.run_commits(), muted():
            MaintenanceTicket.objects.create(unit=self.lease.unit, reported_by=self.admin_a, description="x", priority="URGENT")
        self.assertEqual(len(mail.outbox), 2)

    def test_demo_request(self):
        self.verify(make_user(is_staff=True), "equipe@dahoo.sn")
        with self.run_commits():
            DemoRequest.objects.create(agency_name="Keur Immo", contact_name="Fatou", phone="+221771234567", email="fatou@gmail.com", units_range="1-20")
        self.assertEqual(sorted(message.to[0] for message in mail.outbox), ["equipe@dahoo.sn", "fatou@gmail.com"])
        self.assertTrue(LeaseContract.objects.exists())
