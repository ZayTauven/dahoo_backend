"""Tableau de bord de la plateforme : accès réservé, statuts des agences, revenu, essais, démos."""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from organizations.models import Organization
from public.models import DemoRequest
from subscriptions.models import Subscription, SubscriptionPlan

from .factories import DahooTestCase, client_for, make_listing, make_user

URL = "/api/v1/platform/dashboard/"


class PlatformDashboardTests(DahooTestCase):
    def setUp(self):
        super().setUp()
        self.staff = client_for(make_user(is_staff=True))
        # org_a : abonnée (plan mensuel 50 000) ; org_b : essai qui se termine dans 5 jours.
        monthly = SubscriptionPlan.objects.create(name="Pro", billing_type="MONTHLY", price=Decimal("50000"))
        Subscription.objects.create(organization=self.org_a, plan=monthly, start_date=timezone.localdate() - timedelta(days=10))
        Organization.objects.filter(pk=self.org_b.pk).update(trial_ends_at=timezone.now() + timedelta(days=5))
        # Agence expirée, agence suspendue, et l'organisation interne (exclue des comptes).
        Organization.objects.create(name="Expirée", trial_ends_at=timezone.now() - timedelta(days=1))
        Organization.objects.create(name="Suspendue", is_active=False)
        Organization.objects.create(name="Dahoo", is_internal=True)
        yearly = SubscriptionPlan.objects.create(name="Réseau", billing_type="YEARLY", price=Decimal("1200000"))
        other = Organization.objects.create(name="Annuelle")
        Subscription.objects.create(organization=other, plan=yearly, start_date=timezone.localdate())
        make_listing(self.org_a)
        DemoRequest.objects.create(agency_name="Teranga Immo", contact_name="Awa", phone="+221770000099", units_range="1-20")
        DemoRequest.objects.create(agency_name="Déjà traitée", contact_name="Moussa", phone="+221770000098", units_range="1-20", handled=True)

    def test_reserved_to_platform_admins(self):
        self.assertEqual(self.api_a.get(URL).status_code, 403)
        self.assertEqual(self.staff.get(URL).status_code, 200)

    def test_figures(self):
        data = self.staff.get(URL).json()
        self.assertEqual(data["agencies"]["total"], 5)  # l'organisation interne n'est pas comptée
        self.assertEqual(data["agencies"]["by_status"], {"ACTIVE": 2, "TRIAL": 1, "EXPIRED": 1, "SUSPENDED": 1})
        self.assertEqual(data["subscriptions"]["active"], 2)
        self.assertEqual(Decimal(data["subscriptions"]["mrr"]), Decimal("150000"))
        self.assertEqual([trial["id"] for trial in data["trials_ending"]], [self.org_b.id])
        self.assertEqual(data["demo_requests"]["pending"], 1)
        self.assertEqual(data["demo_requests"]["recent_pending"][0]["agency_name"], "Teranga Immo")
        self.assertEqual(data["portal"]["listings_published"], 1)
        self.assertEqual(data["top_agencies"][0]["id"], self.org_a.id)
        self.assertEqual(len(data["monthly"]), 12)
        self.assertEqual(sum(month["demo_requests"] for month in data["monthly"]), 2)

    def test_six_months(self):
        self.assertEqual(len(self.staff.get(URL, {"months": 6}).json()["monthly"]), 6)
