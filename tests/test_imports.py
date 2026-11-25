"""Reprise d'un parc depuis un tableur : lecture tolérante, contrôle sans écriture, création en une fois."""

import zipfile
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from django.utils import timezone
from openpyxl import Workbook, load_workbook

from imports import values
from imports.reader import Cell
from leases.models import LeaseContract, Tenant
from organizations.models import Organization
from owners.models import Owner
from payments.models import PaymentSchedule
from payments.services import due_schedules
from properties.models import Property, Unit
from subscriptions.models import Subscription, SubscriptionPlan
from users.models import User

from .factories import (
    DahooTestCase, add_member, client_for, make_lease, make_owner, make_tenant, make_unit, payment_method,
)

URL = "/api/v1/imports/"
HEADERS = [
    "Bien", "Bâtiment", "Lot", "Catégorie", "Nom bailleur", "Téléphone bailleur", "Commission (%)",
    "Nom locataire", "Téléphone locataire", "Loyer", "Charges", "Caution", "Début du bail", "Impayé à reprendre",
]


def row(**fields):
    base = dict.fromkeys(HEADERS)
    base.update({"Bien": "Résidence Mermoz", "Lot": "A1", **fields})
    return base


RENTED = {
    "Nom bailleur": "Seynabou Diagne", "Téléphone bailleur": "77 666 01 01", "Commission (%)": 10,
    "Nom locataire": "Mamadou Diallo", "Téléphone locataire": 775550101, "Loyer": "450 000 F CFA", "Charges": 30000,
    "Caution": 900000, "Début du bail": "01/03/2024",
}


def xlsx(rows, headers=HEADERS, sheet="Parc locatif", name="parc.xlsx"):
    workbook = Workbook()
    page = workbook.active
    page.title = sheet
    page.append(headers)
    for item in rows:
        page.append([item.get(header) for header in headers])
    buffer = BytesIO()
    workbook.save(buffer)
    return SimpleUploadedFile(name, buffer.getvalue())


class ValueTests(SimpleTestCase):
    def test_money(self):
        for raw, expected in [
            ("150 000 F CFA", 150000), ("150.000", 150000), ("1,250,000", 1250000), (150000, 150000), (150000.0, 150000),
            ("150000 FCFA", 150000), ("150000,00", 150000), ("75 000 F", 75000),
        ]:
            with self.subTest(raw=raw):
                self.assertEqual(values.money(Cell(raw)), expected)
        for raw in ("-5000", "beaucoup", "1e9", "=A1"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                values.money(Cell(raw))

    def test_phone(self):
        for raw in ("77 123 45 67", 771234567, 771234567.0, "+221771234567", 221771234567, "00221 77 123 45 67"):
            with self.subTest(raw=raw):
                self.assertEqual(values.phone(Cell(raw)), "+221771234567")
        for raw in ("77 123 45 67 / 76 000 00 00", "123", "abc"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                values.phone(Cell(raw))

    def test_day(self):
        for raw in ("05/11/2026", "5-11-2026", "2026-11-05", date(2026, 11, 5), 46331):
            with self.subTest(raw=raw):
                self.assertEqual(values.day(Cell(raw)), date(2026, 11, 5))
        for raw in ("31/02/2026", "novembre", "05/11/26"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                values.day(Cell(raw))

    def test_percent(self):
        for cell, expected in [(Cell("10%"), "10"), (Cell(10), "10"), (Cell(0.1, percent=True), "10"), (Cell("7,5"), "7.5")]:
            self.assertEqual(values.percent(cell), Decimal(expected))
        with self.assertRaises(ValueError):
            values.percent(Cell(120))


class ImportTestCase(DahooTestCase):
    def preview(self, rows, api=None, **options):
        return (api or self.api_a).post(f"{URL}preview/", {"file": xlsx(rows, **options)}, format="multipart")

    def commit(self, rows, api=None, **fields):
        return (api or self.api_a).post(f"{URL}commit/", {"file": xlsx(rows), **fields}, format="multipart")

    def messages(self, response, index=0):
        return " ".join(message["text"] for message in response.json()["rows"][index]["messages"])


class PreviewTests(ImportTestCase):
    def test_nothing_is_written(self):
        response = self.preview([row(**RENTED), row(Lot="A2")])
        self.assertEqual(response.status_code, 200, response.content)
        summary = response.json()["summary"]
        self.assertEqual(
            [summary[key] for key in ("rows", "ready", "errors", "properties", "units", "owners", "tenants", "leases")],
            [2, 2, 0, 1, 2, 1, 1, 1],
        )
        self.assertEqual(Decimal(summary["monthly_rent"]), Decimal("480000"))
        self.assertEqual(response.json()["rows"][0]["tenant_name"], "Mamadou Diallo")
        for model in (Property, Unit, Tenant, Owner, LeaseContract):
            self.assertFalse(model.objects.exists())

    def test_errors_are_located(self):
        cases = {
            "Le téléphone du locataire est obligatoire.": {**RENTED, "Téléphone locataire": None},
            "Le loyer est obligatoire": {**RENTED, "Loyer": None},
            "Montant « beaucoup » invalide": {**RENTED, "Loyer": "beaucoup"},
            "Date « hier » invalide": {**RENTED, "Début du bail": "hier"},
            "« Lot » est obligatoire": {"Lot": None, "Catégorie": "Studio"},
            "Impayé sans locataire": {"Impayé à reprendre": 5000},
            "Le téléphone du bailleur est obligatoire": {"Nom bailleur": "Seynabou"},
        }
        for expected, fields in cases.items():
            with self.subTest(expected=expected):
                response = self.preview([row(**fields)])
                self.assertEqual(response.json()["rows"][0]["status"], "ERROR")
                self.assertIn(expected, self.messages(response))
                self.assertEqual(response.json()["rows"][0]["line"], 2)

    def test_conflicts_inside_the_file(self):
        response = self.preview([
            row(**RENTED),
            row(),
            row(Lot="A3", **{**RENTED, "Nom locataire": "Autre Personne"}),
            row(Lot="A4", **{"Nom bailleur": "Autre Bailleur", "Téléphone bailleur": "77 000 00 99"}),
        ])
        self.assertIn("Lot déjà présent à la ligne 2", self.messages(response, 1))
        self.assertIn("Ce numéro est celui de Mamadou Diallo à la ligne 2", self.messages(response, 2))
        self.assertIn("Un autre bailleur est indiqué pour ce bien à la ligne 2", self.messages(response, 3))

    def test_one_tenant_may_rent_two_units(self):
        response = self.preview([row(**RENTED), row(Lot="A2", **RENTED)])
        self.assertEqual(response.json()["summary"]["errors"], 0)
        self.assertEqual(response.json()["summary"]["tenants"], 1)

    def test_soft_warnings(self):
        response = self.preview([row(**{**RENTED, "Début du bail": None, "Catégorie": "Penthouse"})])
        self.assertEqual(response.json()["rows"][0]["status"], "WARNING")
        self.assertIn("Penthouse", self.messages(response))
        self.assertIn("retenu", self.messages(response))

    def test_unknown_columns_and_free_header_names(self):
        headers = ["Immeuble", "Référence", "Locataire", "Tél", "Loyer mensuel", "Couleur"]
        rows = [{"Immeuble": "Villa Ngor", "Référence": 12, "Locataire": "Awa Sow", "Tél": "78 111 22 33", "Loyer mensuel": 200000, "Couleur": "bleu"}]
        data = self.preview(rows, headers=headers).json()
        self.assertEqual(data["ignored_columns"], ["Couleur"])
        self.assertEqual((data["rows"][0]["unit"], data["rows"][0]["tenant_name"]), ("12", "Awa Sow"))

    def test_csv_with_semicolons_and_windows_encoding(self):
        content = "Bien;Lot;Nom locataire;Téléphone locataire;Loyer\r\nRésidence Été;A1;Aïssatou Sarr;771112233;150 000\r\n".encode("cp1252")
        response = self.api_a.post(f"{URL}preview/", {"file": SimpleUploadedFile("parc.csv", content)}, format="multipart")
        self.assertEqual(response.json()["rows"][0]["property_name"], "Résidence Été")
        self.assertEqual(response.json()["rows"][0]["tenant_name"], "Aïssatou Sarr")

    def test_bad_files(self):
        bomb = BytesIO()
        with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("xl/workbook.xml", b"0" * (41 * 1024 * 1024))
        files = {
            "pas un excel": SimpleUploadedFile("parc.xlsx", b"bonjour"),
            "ancien format": SimpleUploadedFile("parc.xls", b"x"),
            "format inconnu": SimpleUploadedFile("parc.pdf", b"x"),
            "trop lourd": SimpleUploadedFile("parc.csv", b"x" * (2 * 1024 * 1024 + 1)),
            "archive piégée": SimpleUploadedFile("parc.xlsx", bomb.getvalue()),
            "sans en-tête": xlsx([{"a": 1}], headers=["a"]),
            "vide": xlsx([]),
            "colonne en double": xlsx([{"Bien": "X"}], headers=["Bien", "Lot", "Bien"]),
            "trop de lignes": xlsx([row(Lot=f"L{index}") for index in range(501)]),
        }
        for label, upload in files.items():
            with self.subTest(label=label):
                response = self.api_a.post(f"{URL}preview/", {"file": upload}, format="multipart")
                self.assertEqual(response.status_code, 400, label)
                self.assertIn("file", response.json())


class CommitTests(ImportTestCase):
    def test_everything_is_created(self):
        today = timezone.localdate()
        response = self.commit([
            row(**{**RENTED, "Impayé à reprendre": 480000}),
            row(Lot="A2", Catégorie="Studio"),
        ])
        self.assertEqual(response.status_code, 201, response.content)
        prop = Property.objects.get()
        self.assertEqual((prop.organization, prop.owner.full_name, prop.commission_rate), (self.org_a, "Seynabou Diagne", Decimal("10")))
        lease = LeaseContract.objects.get()
        self.assertEqual((lease.status, lease.unit.status, lease.tenant.phone), ("ACTIVE", "RENTED", "+221775550101"))
        self.assertTrue(lease.auto_schedules)
        self.assertEqual(Unit.objects.get(reference="A2").status, "FREE")
        # Ni les mois passés, ni la caution : le mois en cours et l'impayé repris.
        rents = lease.schedules.filter(schedule_type="RENT")
        self.assertTrue(all(schedule.due_date >= today.replace(day=1) for schedule in rents))
        self.assertFalse(lease.schedules.filter(schedule_type="DEPOSIT").exists())
        arrears = lease.schedules.get(schedule_type="ARREARS")
        self.assertEqual((arrears.amount_due, arrears.due_date), (Decimal("480000"), today.replace(day=1) - timedelta(days=1)))
        self.assertFalse(User.objects.get(phone="+221775550101").has_usable_password())

    def test_first_rent_next_month(self):
        self.commit([row(**RENTED)], first_period="NEXT")
        first_day_next = (timezone.localdate().replace(day=1) + timedelta(days=32)).replace(day=1)
        self.assertTrue(all(s.due_date >= first_day_next for s in PaymentSchedule.objects.all()))

    def test_future_lease_stays_a_draft(self):
        start = timezone.localdate() + timedelta(days=20)
        self.commit([row(**{**RENTED, "Début du bail": f"{start:%d/%m/%Y}"})])
        lease = LeaseContract.objects.get()
        self.assertEqual((lease.status, lease.unit.status), ("DRAFT", "FREE"))
        self.assertFalse(PaymentSchedule.objects.exists())

    def test_sending_the_file_twice_creates_nothing(self):
        rows = [row(**RENTED), row(Lot="A2")]
        self.commit(rows)
        data = self.preview(rows).json()
        self.assertEqual((data["summary"]["skipped"], data["summary"]["ready"]), (2, 0))
        self.assertEqual(self.commit(rows).status_code, 400)
        self.assertEqual((Unit.objects.count(), LeaseContract.objects.count()), (2, 1))

    def test_lease_is_added_to_an_existing_free_unit(self):
        unit = make_unit(self.org_a, reference="A1")
        self.commit([row(**{**RENTED, "Bien": "résidence", "Bâtiment": "BATIMENT A"})])
        self.assertEqual(LeaseContract.objects.get().unit, unit)
        self.assertEqual(Property.objects.count(), 1)
        self.assertEqual(Property.objects.get().owner.full_name, "Seynabou Diagne")

    def test_unit_rented_to_someone_else_is_refused(self):
        unit = make_unit(self.org_a, reference="A1", status="RENTED")
        make_lease(self.org_a, unit=unit, tenant=make_tenant(self.org_a), status="ACTIVE")
        response = self.preview([row(**{**RENTED, "Bien": "Résidence", "Bâtiment": "Bâtiment A"})])
        self.assertIn("déjà un bail actif avec un autre locataire", self.messages(response))

    def test_property_of_another_owner_is_refused(self):
        unit = make_unit(self.org_a, reference="Z9")
        Property.objects.update(owner=make_owner(self.org_a))
        self.assertIsNotNone(unit)
        response = self.preview([row(**{**RENTED, "Bien": "Résidence"})])
        self.assertIn("Ce bien appartient déjà à Fatou Ndiaye", self.messages(response))

    def test_errors_block_unless_skipped(self):
        rows = [row(**RENTED), row(Lot="A2", **{**RENTED, "Téléphone locataire": "abc"})]
        self.assertEqual(self.commit(rows).status_code, 400)
        self.assertFalse(Property.objects.exists())
        self.assertEqual(self.commit(rows, skip_errors=True).status_code, 201)
        self.assertEqual(Unit.objects.count(), 1)

    def test_isolation(self):
        self.commit([row(**RENTED)])
        # L'agence B importe le même fichier : ses propres fiches, le même compte.
        self.assertEqual(self.commit([row(**RENTED)], api=self.api_b).status_code, 201)
        self.assertEqual(Property.objects.filter(organization=self.org_b).count(), 1)
        self.assertEqual(Tenant.objects.count(), 2)
        self.assertEqual(User.objects.filter(phone="+221775550101").count(), 1)

    def test_rights(self):
        for role, expected in (("MANAGER", 200), ("ACCOUNTANT", 403), ("VIEWER", 403)):
            with self.subTest(role=role):
                api = client_for(add_member(self.org_a, role=role))
                self.assertEqual(self.preview([row()], api=api).status_code, expected)
                self.assertEqual(api.get(f"{URL}template/").status_code, expected)

    def test_expired_trial_is_read_only(self):
        Organization.objects.filter(pk=self.org_a.pk).update(trial_ends_at=timezone.now() - timedelta(days=1))
        self.assertEqual(self.commit([row()]).status_code, 402)

    def test_quota_of_the_plan(self):
        plan = SubscriptionPlan.objects.create(name="Petit", billing_type="MONTHLY", price=1, max_units=1)
        Subscription.objects.create(organization=self.org_a, plan=plan, status="ACTIVE", start_date=timezone.localdate())
        rows = [row(), row(Lot="A2")]
        self.assertIn("1 lots, le fichier en ajoute 2", self.preview(rows).json()["problems"][0])
        self.assertEqual(self.commit(rows).status_code, 400)
        self.assertFalse(Unit.objects.exists())

    def test_owner_account_ignores_owner_columns(self):
        Organization.objects.filter(pk=self.org_a.pk).update(kind="OWNER")
        self.commit([row(**RENTED)])
        self.assertIsNone(Property.objects.get().owner)
        headers = [cell.value for cell in load_workbook(BytesIO(self.api_a.get(f"{URL}template/").content))["Parc locatif"][1]]
        self.assertNotIn("Nom bailleur", headers)

    def test_arrears_are_collected_first_and_owed_to_the_owner(self):
        self.commit([row(**{**RENTED, "Impayé à reprendre": 100000})])
        lease = LeaseContract.objects.get()
        self.assertEqual(due_schedules(lease).first().schedule_type, "ARREARS")
        response = self.api_a.post(
            "/api/v1/payments/collect/", {"lease": lease.id, "amount": "100000", "payment_method": payment_method().id}, format="json"
        )
        self.assertEqual(response.json()["receipts"], [])
        payment = response.json()["payment"]["id"]
        self.assertEqual(self.api_a.get(f"/api/v1/payments/payments/{payment}/receipt/").status_code, 200)
        owner = Owner.objects.get()
        self.assertEqual(Decimal(self.api_a.get(f"/api/v1/owners/{owner.id}/").json()["balance"]), Decimal("90000"))


class TemplateTests(ImportTestCase):
    def test_the_example_sheet_is_valid_once_copied(self):
        content = self.api_a.get(f"{URL}template/").content
        workbook = load_workbook(BytesIO(content))
        self.assertEqual(workbook.sheetnames, ["Parc locatif", "Exemple", "Mode d'emploi"])
        # Le modèle vide ne s'importe pas tel quel, et ses exemples non plus.
        empty = SimpleUploadedFile("modele.xlsx", content)
        self.assertEqual(self.api_a.post(f"{URL}preview/", {"file": empty}, format="multipart").status_code, 400)
        for line in workbook["Exemple"].iter_rows(min_row=2):
            for cell in line:
                workbook["Parc locatif"].cell(row=cell.row, column=cell.column, value=cell.value)
        filled = BytesIO()
        workbook.save(filled)
        response = self.api_a.post(f"{URL}preview/", {"file": SimpleUploadedFile("parc.xlsx", filled.getvalue())}, format="multipart")
        self.assertEqual(response.json()["summary"]["errors"], 0, response.json()["rows"])
        self.assertEqual(response.json()["summary"]["ready"], 3)
