"""Espace agence : filtres, recherche, tri et libellés en lecture seule des listes."""

from datetime import datetime, timezone as dt_timezone

from django.db import connection
from django.test.utils import CaptureQueriesContext

from leases.models import Tenant
from maintenance.models import MaintenanceCategory, MaintenanceTicket
from payments.models import Payment, PaymentSchedule
from properties.models import Building, Property

from .factories import (
    DahooTestCase,
    make_lease,
    make_listing,
    make_org,
    make_schedule,
    make_tenant,
    make_unit,
    payment_method,
    results,
)


def ids(response):
    assert response.status_code == 200, response.content
    return [item["id"] for item in results(response)]


class PropertyAndUnitScreenTests(DahooTestCase):
    def setUp(self):
        super().setUp()
        self.dakar = Property.objects.create(organization=self.org_a, name="Résidence Teranga", address="Rue 10", city="Dakar")
        self.thies = Property.objects.create(organization=self.org_a, name="Villa Baobab", address="Route de Mbour", city="Thiès")
        building = Building.objects.create(property=self.dakar, name="Bâtiment A")
        Building.objects.create(property=self.dakar, name="Bâtiment B")
        self.a101 = building.units.create(reference="A101", unit_type="T2", surface=60, status="RENTED")
        self.a102 = building.units.create(reference="A102", unit_type="Studio", surface=25, status="FREE", category="STUDIO")
        self.office = make_unit(self.org_a, category="OFFICE")
        self.other_org_unit = make_unit(self.org_b)

    def test_property_filters_and_search(self):
        url = "/api/v1/properties/properties/"
        self.assertEqual(ids(self.api_a.get(f"{url}?city=dakar")), [self.office.building.property_id, self.dakar.id])
        self.assertEqual(ids(self.api_a.get(f"{url}?search=baobab")), [self.thies.id])
        self.assertEqual(ids(self.api_a.get(f"{url}?search=mbour")), [self.thies.id])
        names = [item["name"] for item in results(self.api_a.get(f"{url}?ordering=name"))]
        self.assertEqual(names, sorted(names))

    def test_property_counters(self):
        data = self.api_a.get(f"/api/v1/properties/properties/{self.dakar.id}/").json()
        self.assertEqual(
            (data["buildings_count"], data["units_count"], data["occupied_units_count"]), (2, 2, 1)
        )

    def test_units_of_building_filters(self):
        url = f"/api/v1/properties/buildings/{self.a101.building_id}/units/"
        self.assertEqual(ids(self.api_a.get(f"{url}?status=FREE")), [self.a102.id])
        self.assertEqual(ids(self.api_a.get(f"{url}?category=STUDIO")), [self.a102.id])

    def test_flat_unit_list(self):
        url = "/api/v1/properties/units/"
        self.assertEqual(set(ids(self.api_a.get(url))), {self.a101.id, self.a102.id, self.office.id})
        self.assertEqual(ids(self.api_a.get(f"{url}?category=OFFICE")), [self.office.id])
        self.assertEqual(ids(self.api_a.get(f"{url}?status=RENTED")), [self.a101.id])
        self.assertEqual(set(ids(self.api_a.get(f"{url}?building={self.a101.building_id}"))), {self.a101.id, self.a102.id})
        # Un lot d'une autre agence ne ressort jamais, même filtré par son bâtiment.
        self.assertEqual(ids(self.api_a.get(f"{url}?building={self.other_org_unit.building_id}")), [])
        unit = next(item for item in results(self.api_a.get(url)) if item["id"] == self.a101.id)
        self.assertEqual(unit["label"], "Résidence Teranga · Bâtiment A · A101")
        self.assertEqual(unit["category_label"], "Appartement")

    def test_unit_features_are_writable(self):
        response = self.api_a.patch(
            f"/api/v1/properties/units/{self.a102.id}/",
            {"bedrooms": 1, "bathrooms": 1, "parking_spaces": 0, "is_furnished": True, "category": "STUDIO"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["is_furnished"])
        response = self.api_a.patch(
            f"/api/v1/properties/properties/{self.dakar.id}/",
            {"neighborhood": "Mermoz", "latitude": "14.716677", "longitude": "-17.467686"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["latitude"], "14.716677")
        bad = self.api_a.patch(f"/api/v1/properties/properties/{self.dakar.id}/", {"latitude": "95"}, format="json")
        self.assertEqual(bad.status_code, 400)

    def test_unknown_ordering_is_ignored(self):
        # Libellé calculé : non triable, ignoré au lieu d'une erreur 500.
        self.assertEqual(self.api_a.get("/api/v1/properties/units/?ordering=label").status_code, 200)
        self.assertEqual(self.api_a.get("/api/v1/leases/?ordering=tenant_name").status_code, 200)


class LeaseScreenTests(DahooTestCase):
    def setUp(self):
        super().setUp()
        self.tenant = make_tenant(self.org_a, first_name="Ibrahima", last_name="Sarr")
        self.other_tenant = make_tenant(self.org_a, first_name="Aminata", last_name="Ba")
        self.active = make_lease(self.org_a, tenant=self.tenant, status="ACTIVE")
        self.draft = make_lease(self.org_a, tenant=self.other_tenant)

    def test_filters(self):
        self.assertEqual(ids(self.api_a.get("/api/v1/leases/?status=ACTIVE")), [self.active.id])
        self.assertEqual(ids(self.api_a.get(f"/api/v1/leases/?tenant={self.other_tenant.id}")), [self.draft.id])
        self.assertEqual(ids(self.api_a.get(f"/api/v1/leases/?unit={self.active.unit_id}")), [self.active.id])

    def test_labels_use_the_agency_tenant_record(self):
        # La fiche locataire de l'agence prime sur le nom du compte.
        Tenant.objects.filter(organization=self.org_a, user=self.tenant).update(first_name="Ibou")
        lease = next(item for item in results(self.api_a.get("/api/v1/leases/")) if item["id"] == self.active.id)
        self.assertEqual(lease["tenant_name"], "Ibou Sarr")
        self.assertEqual(lease["unit_label"], f"Résidence · Bâtiment A · {self.active.unit.reference}")
        detail = self.api_a.get(f"/api/v1/leases/{self.active.id}/").json()
        self.assertEqual(detail["tenant_name"], "Ibou Sarr")

    def test_no_query_per_row(self):
        with CaptureQueriesContext(connection) as few:
            self.api_a.get("/api/v1/leases/")
        for _ in range(4):
            make_lease(self.org_a, tenant=make_tenant(self.org_a))
        with CaptureQueriesContext(connection) as many:
            response = self.api_a.get("/api/v1/leases/")
        self.assertEqual(len(results(response)), 6)
        self.assertEqual(len(many), len(few))

    def test_tenant_search(self):
        url = "/api/v1/leases/tenants/"
        self.assertEqual(ids(self.api_a.get(f"{url}?search=aminata")), [self.other_tenant.id])
        self.assertEqual(ids(self.api_a.get(f"{url}?search=ibrahima sarr")), [self.tenant.id])
        self.assertEqual(ids(self.api_a.get(f"{url}?search={self.tenant.phone[-6:]}")), [self.tenant.id])
        self.assertEqual(ids(self.api_b.get(f"{url}?search=aminata")), [])


class PaymentScreenTests(DahooTestCase):
    def setUp(self):
        super().setUp()
        self.tenant = make_tenant(self.org_a, first_name="Ibrahima", last_name="Sarr")
        self.lease = make_lease(self.org_a, tenant=self.tenant, status="ACTIVE")
        self.february = make_schedule(self.lease)
        self.march = PaymentSchedule.objects.create(
            organization=self.org_a, lease_contract=self.lease, schedule_type="RENT",
            due_date="2026-03-01", amount_due=150000, is_paid=True,
        )
        self.other_lease = make_lease(self.org_a, tenant=make_tenant(self.org_a))
        self.other_schedule = make_schedule(self.other_lease)

    def test_schedule_filters_and_label(self):
        url = "/api/v1/payments/schedules/"
        self.assertEqual(ids(self.api_a.get(f"{url}?is_paid=true")), [self.march.id])
        self.assertEqual(
            ids(self.api_a.get(f"{url}?lease_contract={self.lease.id}&due_date_after=2026-02-15")), [self.march.id]
        )
        self.assertEqual(
            set(ids(self.api_a.get(f"{url}?due_date_before=2026-02-01"))), {self.february.id, self.other_schedule.id}
        )
        schedule = self.api_a.get(f"{url}{self.february.id}/").json()
        self.assertEqual(schedule["contract_label"], f"Bail n°{self.lease.id} · Ibrahima Sarr · {self.lease.unit.reference}")

    def test_payment_filters_and_payer_name(self):
        method = payment_method()
        paid = Payment.objects.create(
            organization=self.org_a, payer=self.tenant, recorded_by=self.admin_a, amount_paid=150000, payment_method=method
        )
        other = Payment.objects.create(
            organization=self.org_a, payer=self.other_lease.tenant, recorded_by=self.admin_a,
            amount_paid=1000, payment_method=method,
        )
        Payment.objects.filter(pk=other.pk).update(payment_date=datetime(2026, 1, 10, tzinfo=dt_timezone.utc))
        Payment.objects.filter(pk=paid.pk).update(payment_date=datetime(2026, 3, 5, tzinfo=dt_timezone.utc))
        url = "/api/v1/payments/payments/"
        self.assertEqual(ids(self.api_a.get(f"{url}?payer={self.tenant.id}")), [paid.id])
        self.assertEqual(ids(self.api_a.get(f"{url}?payment_date_after=2026-03-01")), [paid.id])
        self.assertEqual(ids(self.api_a.get(f"{url}?payment_date_before=2026-01-10")), [other.id])
        self.assertEqual(ids(self.api_a.get(f"{url}?ordering=amount_paid")), [other.id, paid.id])
        payment = results(self.api_a.get(f"{url}?payer={self.tenant.id}"))[0]
        self.assertEqual(payment["payer_name"], "Ibrahima Sarr")

    def test_payment_creation_answer_has_payer_name(self):
        response = self.api_a.post(
            "/api/v1/payments/payments/",
            {"payer": self.tenant.id, "amount_paid": "150000", "payment_method": payment_method().id},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["payer_name"], "Ibrahima Sarr")


class TicketAndListingScreenTests(DahooTestCase):
    def test_ticket_filters_and_labels(self):
        plumbing = MaintenanceCategory.objects.create(code="PLUMBING", label="Plomberie")
        unit = make_unit(self.org_a)
        urgent = MaintenanceTicket.objects.create(
            unit=unit, category=plumbing, reported_by=self.admin_a, description="Fuite", priority="URGENT"
        )
        closed = MaintenanceTicket.objects.create(
            unit=make_unit(self.org_a), reported_by=self.admin_a, description="Ampoule", status="CLOSED"
        )
        url = "/api/v1/maintenance/tickets/"
        self.assertEqual(ids(self.api_a.get(f"{url}?status=CLOSED")), [closed.id])
        self.assertEqual(ids(self.api_a.get(f"{url}?priority=URGENT")), [urgent.id])
        self.assertEqual(ids(self.api_a.get(f"{url}?unit={unit.id}")), [urgent.id])
        tickets = {item["id"]: item for item in results(self.api_a.get(url))}
        self.assertEqual(tickets[urgent.id]["category_label"], "Plomberie")
        self.assertEqual(tickets[urgent.id]["unit_label"], f"Résidence · Bâtiment A · {unit.reference}")
        self.assertIsNone(tickets[closed.id]["category_label"])

    def test_listing_filters(self):
        rent = make_listing(self.org_a, status="DRAFT")
        sale = make_listing(self.org_a, listing_type="SALE")
        make_listing(self.org_b)
        url = "/api/v1/listings/"
        self.assertEqual(ids(self.api_a.get(f"{url}?status=DRAFT")), [rent.id])
        self.assertEqual(ids(self.api_a.get(f"{url}?listing_type=SALE")), [sale.id])
        self.assertEqual(ids(self.api_a.get(f"{url}?status=PUBLISHED&listing_type=RENT")), [])
        listing = results(self.api_a.get(f"{url}?listing_type=SALE"))[0]
        self.assertEqual((listing["cover"], listing["photos_count"]), (None, 0))


class NoQueryPerRowTests(DahooTestCase):
    """Le nombre de requêtes d'une liste ne dépend pas du nombre de lignes (libellés via select_related/annotations)."""

    URLS = [
        "/api/v1/properties/properties/",
        "/api/v1/properties/units/",
        "/api/v1/payments/schedules/",
        "/api/v1/payments/payments/",
        "/api/v1/maintenance/tickets/",
        "/api/v1/listings/",
        "/api/v1/public/listings/",
        "/api/v1/public/agencies/",
    ]

    def add_rows(self):
        tenant = make_tenant(self.org_a)
        lease = make_lease(self.org_a, tenant=tenant, status="ACTIVE")
        make_schedule(lease)
        Payment.objects.create(
            organization=self.org_a, payer=tenant, recorded_by=self.admin_a, amount_paid=1000, payment_method=payment_method()
        )
        MaintenanceTicket.objects.create(
            unit=lease.unit, category=MaintenanceCategory.objects.get_or_create(code="ELEC", label="Électricité")[0],
            reported_by=self.admin_a, description="Panne",
        )
        listing = make_listing(self.org_a, unit=lease.unit)
        listing.photos.create(image="listings/2026/09/a.jpg")
        make_listing(make_org("Agence publique"))  # visible sur le portail

    def count_queries(self):
        counts = {}
        for url in self.URLS:
            with CaptureQueriesContext(connection) as queries:
                response = self.api_a.get(url)
            self.assertEqual(response.status_code, 200, (url, response.content))
            counts[url] = len(queries)
        return counts

    def test_query_count_is_constant(self):
        self.add_rows()
        few = self.count_queries()
        for _ in range(3):
            self.add_rows()
        self.assertEqual(self.count_queries(), few)


class ScheduleLabelUpdateTests(DahooTestCase):
    def test_label_follows_contract_change(self):
        first = make_lease(self.org_a, tenant=make_tenant(self.org_a, first_name="Awa", last_name="Diallo"))
        second = make_lease(self.org_a, tenant=make_tenant(self.org_a, first_name="Modou", last_name="Faye"))
        schedule = make_schedule(first)
        response = self.api_a.patch(
            f"/api/v1/payments/schedules/{schedule.id}/", {"lease_contract": second.id}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("Modou Faye", response.json()["contract_label"])
