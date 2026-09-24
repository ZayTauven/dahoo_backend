"""API publique : visibilité des annonces, absence de données privées, filtres, agences, statistiques, démo."""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework.test import APIClient

from listings.models import ListingPhoto, Prospect
from organizations.models import Organization
from properties.models import Property
from public.models import DemoRequest
from subscriptions.models import Subscription, SubscriptionPlan

from .factories import (
    DahooTestCase,
    add_member,
    client_for,
    make_lease,
    make_listing,
    make_tenant,
    make_unit,
    make_user,
    results,
)

PUBLIC = "/api/v1/public/"
PROSPECT = {"full_name": "Fatou Ndiaye", "phone": "+221779998877", "source": "site"}


def all_keys(data):
    """Toutes les clés présentes à n'importe quelle profondeur d'une réponse JSON."""
    if isinstance(data, dict):
        return set(data) | {key for value in data.values() for key in all_keys(value)}
    if isinstance(data, list):
        return {key for item in data for key in all_keys(item)}
    return set()


class PublicTestCase(DahooTestCase):
    def setUp(self):
        super().setUp()
        self.public = APIClient()

    def listing_ids(self, query=""):
        response = self.public.get(f"{PUBLIC}listings/{query}")
        self.assertEqual(response.status_code, 200, response.content)
        return [item["id"] for item in results(response)]

    def expire_trial(self, organization):
        organization.trial_ends_at = timezone.now() - timedelta(days=1)
        organization.save(update_fields=["trial_ends_at"])


class PublicVisibilityTests(PublicTestCase):
    def setUp(self):
        super().setUp()
        self.visible = make_listing(self.org_a)

    def test_only_published_listings_are_visible(self):
        draft = make_listing(self.org_a, status="DRAFT")
        suspended = make_listing(self.org_a, status="SUSPENDED")
        closed = make_listing(self.org_a, status="CLOSED")
        self.assertEqual(self.listing_ids(), [self.visible.id])
        for hidden in (draft, suspended, closed):
            self.assertEqual(self.public.get(f"{PUBLIC}listings/{hidden.id}/").status_code, 404)

    def test_inactive_organization_is_hidden(self):
        self.org_a.is_active = False
        self.org_a.save()
        self.assertEqual(self.listing_ids(), [])
        self.assertEqual(self.public.get(f"{PUBLIC}listings/{self.visible.id}/").status_code, 404)

    def test_expired_trial_is_hidden_until_subscription(self):
        self.expire_trial(self.org_a)
        self.assertEqual(self.listing_ids(), [])
        plan = SubscriptionPlan.objects.create(name="Pro", billing_type="MONTHLY", price=50000)
        Subscription.objects.create(organization=self.org_a, plan=plan, start_date=timezone.localdate())
        self.assertEqual(self.listing_ids(), [self.visible.id])

    def test_suspended_subscription_does_not_count(self):
        self.expire_trial(self.org_a)
        plan = SubscriptionPlan.objects.create(name="Pro", billing_type="MONTHLY", price=50000)
        Subscription.objects.create(
            organization=self.org_a, plan=plan, start_date=timezone.localdate(), status="SUSPENDED"
        )
        self.assertEqual(self.listing_ids(), [])

    def test_internal_organization_is_always_visible(self):
        dahoo = Organization.objects.create(
            name="Dahoo", is_internal=True, trial_ends_at=timezone.now() - timedelta(days=365)
        )
        listing = make_listing(dahoo)
        self.assertIn(listing.id, self.listing_ids())

    def test_no_interest_on_hidden_listing(self):
        self.expire_trial(self.org_a)
        payload = {"prospect": PROSPECT, "message": "Visite ?"}
        for url in (f"{PUBLIC}listings/{self.visible.id}/interest/", f"/api/v1/listings/{self.visible.id}/interest/"):
            self.assertEqual(self.public.post(url, payload, format="json").status_code, 404)

    def test_public_endpoints_ignore_authentication(self):
        # Un jeton invalide ou expiré envoyé par le front ne doit pas casser le portail.
        self.public.credentials(HTTP_AUTHORIZATION="Bearer jeton-invalide")
        self.assertEqual(self.public.get(f"{PUBLIC}listings/").status_code, 200)


class PublicPrivacyTests(PublicTestCase):
    FORBIDDEN_KEYS = {
        "tenant", "tenant_name", "owner", "prospect", "interests", "created_by",
        "reference", "unit", "status", "rent_amount", "members", "full_name",
    }

    def setUp(self):
        super().setUp()
        self.owner = make_user(phone="+221770001111")
        unit = make_unit(self.org_a, city="Dakar", latitude=Decimal("14.716677"), longitude=Decimal("-17.467686"))
        Property.objects.filter(pk=unit.building.property_id).update(owner=self.owner, address="12 rue Secrète")
        tenant = make_tenant(self.org_a, phone="+221770002222")
        make_lease(self.org_a, unit=unit, tenant=tenant, status="ACTIVE")
        self.listing = make_listing(self.org_a, unit=unit)
        self.public.post(
            f"{PUBLIC}listings/{self.listing.id}/interest/", {"prospect": PROSPECT, "message": "m"}, format="json"
        )
        self.org_a.phone, self.org_a.email = "+221338200000", "contact@agence-a.sn"
        self.org_a.save()

    def assert_no_private_data(self, response):
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        for secret in ("+221770001111", "+221770002222", PROSPECT["phone"], "Fatou", "12 rue Secrète", "150000"):
            self.assertNotIn(secret, content)
        self.assertFalse(all_keys(response.json()) & self.FORBIDDEN_KEYS)

    def test_list_exposes_no_private_data(self):
        response = self.public.get(f"{PUBLIC}listings/")
        self.assert_no_private_data(response)
        self.assertNotIn("phone", all_keys(response.json()))

    def test_detail_exposes_agency_contact_only(self):
        response = self.public.get(f"{PUBLIC}listings/{self.listing.id}/")
        self.assert_no_private_data(response)
        data = response.json()
        self.assertEqual(data["agency"], {
            "id": self.org_a.id, "name": "Agence A", "city": "", "phone": "+221338200000", "email": "contact@agence-a.sn",
        })
        # Position arrondie : le quartier, pas le logement.
        self.assertEqual((data["latitude"], data["longitude"]), ("14.717", "-17.468"))

    def test_agency_and_stats_expose_no_private_data(self):
        self.assert_no_private_data(self.public.get(f"{PUBLIC}agencies/"))
        self.assert_no_private_data(self.public.get(f"{PUBLIC}agencies/{self.org_a.id}/"))
        self.assert_no_private_data(self.public.get(f"{PUBLIC}stats/"))

    def test_interest_answer_hides_prospect(self):
        response = self.public.post(
            f"{PUBLIC}listings/{self.listing.id}/interest/", {"prospect": PROSPECT, "message": "Encore"}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(set(response.json()), {"id", "listing", "created_at"})
        # Même logique que l'ancienne route : prospect dédoublonné par téléphone dans l'agence.
        self.assertEqual(Prospect.objects.filter(organization=self.org_a).count(), 1)
        self.assertEqual(self.listing.interests.count(), 2)


class PublicListingFilterTests(PublicTestCase):
    def setUp(self):
        super().setUp()
        now = timezone.now()
        self.flat = make_listing(
            self.org_a, price="250000", published_at=now - timedelta(days=3), title="F3 Mermoz",
            unit=make_unit(self.org_a, city="Dakar", neighborhood="Mermoz", category="APARTMENT", bedrooms=2),
        )
        self.villa = make_listing(
            self.org_a, price="900000", published_at=now - timedelta(days=1), title="Villa avec piscine",
            unit=make_unit(self.org_a, city="Dakar", neighborhood="Almadies", category="HOUSE", bedrooms=5),
        )
        self.land = make_listing(
            self.org_b, listing_type="SALE", price="25000000", published_at=now - timedelta(days=2),
            unit=make_unit(self.org_b, city="Thiès", category="LAND"),
        )

    def test_default_order_is_most_recent_first(self):
        self.assertEqual(self.listing_ids(), [self.villa.id, self.land.id, self.flat.id])

    def test_ordering_by_price(self):
        self.assertEqual(self.listing_ids("?ordering=price"), [self.flat.id, self.villa.id, self.land.id])
        self.assertEqual(self.listing_ids("?ordering=-price"), [self.land.id, self.villa.id, self.flat.id])

    def test_filters(self):
        self.assertEqual(self.listing_ids("?listing_type=SALE"), [self.land.id])
        self.assertEqual(set(self.listing_ids("?city=dakar")), {self.flat.id, self.villa.id})
        self.assertEqual(self.listing_ids("?category=HOUSE"), [self.villa.id])
        self.assertEqual(self.listing_ids("?min_price=300000&max_price=1000000"), [self.villa.id])
        self.assertEqual(self.listing_ids("?min_bedrooms=3"), [self.villa.id])
        self.assertEqual(self.listing_ids(f"?agency={self.org_b.id}"), [self.land.id])
        self.assertEqual(self.listing_ids("?q=almadies"), [self.villa.id])
        self.assertEqual(self.listing_ids("?q=piscine"), [self.villa.id])
        self.assertEqual(self.listing_ids("?q=thiès"), [self.land.id])

    def test_invalid_filter_is_rejected(self):
        self.assertEqual(self.public.get(f"{PUBLIC}listings/?listing_type=LEASE").status_code, 400)

    def test_list_fields_and_cover(self):
        ListingPhoto.objects.create(listing=self.villa, image="listings/2026/09/second.jpg", position=2)
        ListingPhoto.objects.create(listing=self.villa, image="listings/2026/09/first.jpg", position=1)
        item = next(i for i in results(self.public.get(f"{PUBLIC}listings/")) if i["id"] == self.villa.id)
        self.assertEqual(item["cover"], "http://testserver/media/listings/2026/09/first.jpg")
        self.assertEqual(item["category"], "HOUSE")
        self.assertEqual(item["category_label"], "Maison / villa")
        self.assertEqual(item["neighborhood"], "Almadies")
        self.assertEqual(item["bedrooms"], 5)
        self.assertEqual(item["agency"], {"id": self.org_a.id, "name": "Agence A", "city": ""})
        flat = next(i for i in results(self.public.get(f"{PUBLIC}listings/")) if i["id"] == self.flat.id)
        self.assertIsNone(flat["cover"])

    def test_page_size(self):
        response = self.public.get(f"{PUBLIC}listings/?page_size=2")
        self.assertEqual(len(results(response)), 2)
        self.assertEqual(response.json()["count"], 3)


class PublicListingDetailTests(PublicTestCase):
    def test_detail_with_photos_and_similar(self):
        listing = make_listing(self.org_a, unit=make_unit(self.org_a, city="Dakar", parking_spaces=2))
        ListingPhoto.objects.create(listing=listing, image="listings/2026/09/salon.jpg", alt="Salon", position=0)
        similar = [make_listing(self.org_a) for _ in range(3)] + [make_listing(self.org_b)]
        make_listing(self.org_a, status="DRAFT")  # invisible
        make_listing(self.org_a, listing_type="SALE")  # autre type
        make_listing(self.org_a, unit=make_unit(self.org_a, city="Saly"))  # autre ville

        data = self.public.get(f"{PUBLIC}listings/{listing.id}/").json()
        self.assertEqual(data["description"], "Lumineux")
        self.assertEqual(data["parking_spaces"], 2)
        self.assertEqual(data["photos"], [{"url": "http://testserver/media/listings/2026/09/salon.jpg", "alt": "Salon"}])
        self.assertIsNone(data["latitude"])
        self.assertEqual(len(data["similar"]), 3)
        self.assertTrue({item["id"] for item in data["similar"]} <= {item.id for item in similar})
        self.assertNotIn(listing.id, [item["id"] for item in data["similar"]])


class PublicAgencyTests(PublicTestCase):
    def setUp(self):
        super().setUp()
        self.org_a.city, self.org_a.address = "Dakar", "Avenue Cheikh Anta Diop"
        self.org_a.save()
        make_listing(self.org_a)
        make_listing(self.org_a)
        make_listing(self.org_a, listing_type="SALE")
        make_listing(self.org_a, status="DRAFT")
        make_listing(self.org_b, status="DRAFT")  # agence B : aucune annonce publique

    def test_list_only_agencies_with_public_listings(self):
        data = results(self.public.get(f"{PUBLIC}agencies/"))
        self.assertEqual(data, [{"id": self.org_a.id, "name": "Agence A", "city": "Dakar", "listings_count": 3}])

    def test_detail(self):
        data = self.public.get(f"{PUBLIC}agencies/{self.org_a.id}/").json()
        self.assertEqual(data["listings_count"], 3)
        self.assertEqual(data["listings_by_type"], {"RENT": 2, "SALE": 1})
        self.assertEqual(data["address"], "Avenue Cheikh Anta Diop")

    def test_agency_without_public_listing_is_404(self):
        self.assertEqual(self.public.get(f"{PUBLIC}agencies/{self.org_b.id}/").status_code, 404)
        self.org_a.is_active = False
        self.org_a.save()
        self.assertEqual(self.public.get(f"{PUBLIC}agencies/{self.org_a.id}/").status_code, 404)


class PublicStatsAndPlansTests(PublicTestCase):
    def test_stats(self):
        make_listing(self.org_a, unit=make_unit(self.org_a, city="Dakar", category="HOUSE"))
        make_listing(self.org_a, unit=make_unit(self.org_a, city="dakar"))
        make_listing(self.org_b, listing_type="SALE", unit=make_unit(self.org_b, city="Thiès", category="LAND"))
        make_listing(self.org_b, status="DRAFT", unit=make_unit(self.org_b, city="Saly"))
        data = self.public.get(f"{PUBLIC}stats/").json()
        self.assertEqual(data["listings_count"], 3)
        self.assertEqual(data["agencies_count"], 2)
        self.assertEqual(
            {row["listing_type"]: row["count"] for row in data["by_type"]}, {"RENT": 2, "SALE": 1}
        )
        categories = {row["category"]: row["count"] for row in data["by_category"]}
        self.assertEqual(categories["HOUSE"], 1)
        self.assertEqual(categories["APARTMENT"], 1)
        self.assertEqual(categories["OFFICE"], 0)
        # « Dakar » et « dakar » sont regroupées.
        self.assertEqual([(row["city"].lower(), row["listings_count"]) for row in data["cities"]], [("dakar", 2), ("thiès", 1)])

    def test_plans_are_public_and_active_only(self):
        SubscriptionPlan.objects.create(name="Pro", billing_type="MONTHLY", price=50000, max_units=100)
        SubscriptionPlan.objects.create(name="Ancien", billing_type="MONTHLY", price=10000, active=False)
        data = self.public.get(f"{PUBLIC}plans/").json()
        self.assertEqual([plan["name"] for plan in data], ["Pro"])
        self.assertEqual(data[0]["billing_type_label"], "Mensuel")
        self.assertNotIn("active", data[0])


class DemoRequestTests(PublicTestCase):
    DEMO = {
        "agency_name": "Keur Immo", "contact_name": "Moussa Fall", "phone": "+221 77 123 45 67",
        "email": "moussa@keurimmo.sn", "city": "Dakar", "units_range": "21-100", "message": "Démo svp",
    }

    def test_create_demo_request(self):
        response = self.public.post(f"{PUBLIC}demo-requests/", self.DEMO, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        demo = DemoRequest.objects.get()
        self.assertEqual(demo.phone, "+221771234567")
        self.assertFalse(demo.handled)
        self.assertNotIn("handled", response.json())

    def test_invalid_units_range(self):
        response = self.public.post(f"{PUBLIC}demo-requests/", {**self.DEMO, "units_range": "1000"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_demo_requests_are_throttled(self):
        codes = [self.public.post(f"{PUBLIC}demo-requests/", self.DEMO, format="json").status_code for _ in range(6)]
        self.assertEqual(codes, [201] * 5 + [429])

    def test_platform_can_list_and_mark_handled(self):
        self.public.post(f"{PUBLIC}demo-requests/", self.DEMO, format="json")
        demo = DemoRequest.objects.get()
        platform = client_for(make_user(is_staff=True))
        data = results(platform.get("/api/v1/platform/demo-requests/?handled=false"))
        self.assertEqual([item["id"] for item in data], [demo.id])
        response = platform.patch(
            f"/api/v1/platform/demo-requests/{demo.id}/", {"handled": True, "agency_name": "Autre"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        demo.refresh_from_db()
        self.assertTrue(demo.handled)
        self.assertEqual(demo.agency_name, "Keur Immo")  # seul `handled` est modifiable
        self.assertEqual(results(platform.get("/api/v1/platform/demo-requests/?handled=false")), [])

    def test_platform_demo_requests_reserved_to_dahoo_team(self):
        agency_admin = client_for(add_member(self.org_a))
        self.assertEqual(agency_admin.get("/api/v1/platform/demo-requests/").status_code, 403)
        self.assertEqual(APIClient().get("/api/v1/platform/demo-requests/").status_code, 401)
