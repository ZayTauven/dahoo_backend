"""Notifications de l'espace connecté (cloche) et recherche globale (palette de commandes)."""

from datetime import date
from decimal import Decimal

from django.core.cache import cache
from rest_framework.test import APIClient

from maintenance.models import MaintenanceTicket
from notifications.models import InAppNotification
from notifications.services import sync_reminders
from notifications.signals import muted
from payments.models import Payment

from .factories import (
    DahooTestCase,
    add_member,
    client_for,
    make_lease,
    make_listing,
    make_schedule,
    make_tenant,
    make_unit,
    make_user,
    payment_method,
    results,
)

INAPP = "/api/v1/notifications/inapp/"
PROSPECT = {"full_name": "Fatou Ndiaye", "phone": "+221779998877", "source": "site"}


class InAppNotificationTests(DahooTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()

    def test_visit_request_notifies_the_agency_only(self):
        listing = make_listing(self.org_a, title="Villa Almadies")
        with self.captureOnCommitCallbacks(execute=True):
            response = APIClient().post(
                f"/api/v1/public/listings/{listing.id}/interest/", {"prospect": PROSPECT, "message": "Visite samedi ?"}, format="json"
            )
        self.assertEqual(response.status_code, 201, response.content)
        notification = InAppNotification.objects.get(user=self.admin_a)
        self.assertEqual(notification.kind, "VISIT_REQUEST")
        self.assertEqual(notification.link, f"/espace/annonces/{listing.id}")
        self.assertIn("Villa Almadies", notification.title)
        self.assertFalse(InAppNotification.objects.filter(user=self.admin_b).exists())

    def test_payment_notifies_colleagues_but_not_the_recorder(self):
        accountant = add_member(self.org_a, role="ACCOUNTANT")
        with self.captureOnCommitCallbacks(execute=True):
            Payment.objects.create(
                organization=self.org_a, payer=make_tenant(self.org_a), recorded_by=self.admin_a,
                amount_paid=Decimal("150000"), payment_method=payment_method(),
            )
        self.assertFalse(InAppNotification.objects.filter(user=self.admin_a).exists())
        notification = InAppNotification.objects.get(user=accountant)
        self.assertEqual(notification.title, "Paiement de 150 000 F CFA")

    def test_muted_suppresses_event_notifications(self):
        with muted(), self.captureOnCommitCallbacks(execute=True):
            MaintenanceTicket.objects.create(unit=make_unit(self.org_a), description="Fuite", reported_by=make_user())
        self.assertFalse(InAppNotification.objects.exists())

    def test_overdue_reminder_is_created_once(self):
        lease = make_lease(self.org_a, tenant=make_tenant(self.org_a), status="ACTIVE")
        make_schedule(lease)  # échue le 1er février 2026
        today = date(2026, 2, 11)
        sync_reminders(self.org_a, today=today, force=True)
        sync_reminders(self.org_a, today=today, force=True)
        overdue = InAppNotification.objects.filter(user=self.admin_a, kind="RENT_OVERDUE")
        self.assertEqual(overdue.count(), 1)
        self.assertEqual(overdue.get().link, "/espace/echeances?etat=retard")

    def test_list_is_scoped_to_user_and_active_agency(self):
        second_org_admin = add_member(self.org_b, user=self.admin_a)
        InAppNotification.objects.create(user=self.admin_a, organization=self.org_a, kind="TICKET_CREATED", title="A")
        InAppNotification.objects.create(user=second_org_admin, organization=self.org_b, kind="TICKET_CREATED", title="B")
        InAppNotification.objects.create(user=self.admin_b, organization=self.org_b, kind="TICKET_CREATED", title="Autre")
        titles = [row["title"] for row in results(client_for(self.admin_a, self.org_a).get(INAPP))]
        self.assertEqual(titles, ["A"])

    def test_summary_and_read_all(self):
        for title in ("Un", "Deux"):
            InAppNotification.objects.create(user=self.admin_a, organization=self.org_a, kind="TICKET_CREATED", title=title)
        self.assertEqual(self.api_a.get(f"{INAPP}summary/").json(), {"unread": 2})
        unread = results(self.api_a.get(INAPP, {"unread": "true"}))
        self.assertEqual(len(unread), 2)
        self.api_a.patch(f"{INAPP}{unread[0]['id']}/", {"read": True}, format="json")
        self.assertEqual(self.api_a.post(f"{INAPP}read-all/").json(), {"updated": 1})
        self.assertEqual(self.api_a.get(f"{INAPP}summary/").json(), {"unread": 0})

    def test_platform_admin_without_agency_sees_platform_notifications(self):
        staff = make_user(is_staff=True)
        with self.captureOnCommitCallbacks(execute=True):
            response = APIClient().post(
                "/api/v1/public/demo-requests/",
                {"agency_name": "Immo Thiès", "contact_name": "Moussa", "phone": "+221771112233", "units_range": "21-100"},
                format="json",
            )
        self.assertEqual(response.status_code, 201, response.content)
        rows = results(client_for(staff).get(INAPP))
        self.assertEqual([row["kind"] for row in rows], ["DEMO_REQUEST"])
        self.assertEqual(rows[0]["link"], "/plateforme/demandes")


class SearchTests(DahooTestCase):
    URL = "/api/v1/search/"

    def test_finds_across_types_within_the_agency(self):
        unit = make_unit(self.org_a, city="Saly")
        make_listing(self.org_a, unit=unit, title="Villa avec piscine")
        make_tenant(self.org_a, first_name="Awa", last_name="Ndoye")
        make_tenant(self.org_b, first_name="Awa", last_name="Ndoye")

        data = self.api_a.get(self.URL, {"q": "villa piscine"}).json()
        self.assertEqual([row["type"] for row in data["results"]], ["listing"])
        self.assertTrue(data["results"][0]["link"].startswith("/espace/annonces/"))
        tenants = [row for row in self.api_a.get(self.URL, {"q": "awa ndoye"}).json()["results"] if row["type"] == "tenant"]
        self.assertEqual(len(tenants), 1)
        self.assertTrue(tenants[0]["link"].startswith("/espace/locataires?search="))

    def test_ignores_accents(self):
        make_tenant(self.org_a, first_name="Aïssatou", last_name="Sèye")
        titles = [row["title"] for row in self.api_a.get(self.URL, {"q": "aissatou seye"}).json()["results"]]
        self.assertEqual(titles, ["Aïssatou Sèye"])

    def test_short_query_returns_nothing(self):
        make_unit(self.org_a)
        self.assertEqual(self.api_a.get(self.URL, {"q": "r"}).json()["results"], [])
