"""Entrée et sortie : états des lieux, photos privées, décompte de caution."""

import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from PIL import Image

from deposits.models import DepositSettlement
from deposits.services import build_deposits
from inspections.models import Inspection, InspectionPhoto
from inspections.photos import photo_path
from inspections.services import default_rooms
from leases.models import LeaseContract
from mailing.team import build_digest
from notifications.models import InAppNotification
from owners.statements import build_statement, owner_balances
from payments.models import Payment, PaymentMethod, PaymentSchedule
from payments.rent_roll import build_rent_roll

from .factories import DahooTestCase, add_member, client_for, image_file, make_lease, make_owner, make_tenant, make_unit, payment_method


class MoveOutCase(DahooTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.private = tempfile.mkdtemp()
        cls.enterClassContext(override_settings(PRIVATE_MEDIA_ROOT=cls.private))
        cls.addClassCleanup(shutil.rmtree, cls.private, ignore_errors=True)

    def setUp(self):
        super().setUp()
        self.today = timezone.localdate()
        self.owner = make_owner(self.org_a)
        self.unit = make_unit(self.org_a, status="RENTED", bedrooms=2, bathrooms=1)
        prop = self.unit.building.property
        prop.owner, prop.commission_rate = self.owner, Decimal("10")
        prop.save()
        self.lease = make_lease(self.org_a, unit=self.unit, tenant=make_tenant(self.org_a), status="ACTIVE")
        self.lease.deposit_amount = Decimal("300000")
        self.lease.start_date = self.today - timedelta(days=200)
        self.lease.save()
        self.method = payment_method()

    def url(self, path, lease=None):
        return f"/api/v1/leases/{(lease or self.lease).pk}/{path}"

    def add_schedule(self, kind="RENT", amount=150000, days=-10):
        return PaymentSchedule.objects.create(
            organization=self.org_a, lease_contract=self.lease, schedule_type=kind, due_date=self.today + timedelta(days=days), amount_due=amount
        )

    def pay_deposit(self, amount=300000):
        """Caution demandée puis encaissée dans Dahoo."""
        schedule = self.add_schedule("DEPOSIT", 300000, -200)
        payment = Payment.objects.create(
            organization=self.org_a, payer=self.lease.tenant, recorded_by=self.admin_a, amount_paid=amount, payment_method=self.method
        )
        from payments.services import allocate_payment

        allocate_payment(payment, [{"schedule": schedule, "amount": Decimal(amount)}])
        return schedule

    def end(self, status="terminate", expect=200, **body):
        response = self.api_a.post(self.url(f"{status}/"), body, format="json")
        self.assertEqual(response.status_code, expect, response.content)
        self.lease.refresh_from_db()
        return response.json()

    def deposit(self):
        return self.api_a.get(self.url("deposit/")).json()

    def settle(self, expect=201, **body):
        response = self.api_a.post(self.url("deposit/settle/"), {"method": self.method.pk, **body}, format="json")
        self.assertEqual(response.status_code, expect, response.content)
        return response.json()


class LeaseEndTests(MoveOutCase):
    def test_departure_date(self):
        day = self.today - timedelta(days=3)
        self.assertEqual(self.end(ended_on=day.isoformat())["ended_on"], day.isoformat())

    def test_default_is_today_and_body_is_optional(self):
        self.assertEqual(self.api_a.post(self.url("complete/")).json()["ended_on"], self.today.isoformat())

    def test_date_is_checked(self):
        self.assertIn("ended_on", self.end(expect=400, ended_on=(self.today + timedelta(days=1)).isoformat()))
        self.assertIn("ended_on", self.end(expect=400, ended_on=(self.lease.start_date - timedelta(days=1)).isoformat()))

    def test_archiving_keeps_the_departure_date(self):
        day = (self.today - timedelta(days=5)).isoformat()
        self.end(ended_on=day)
        self.assertEqual(self.api_a.post(self.url("complete/")).json()["ended_on"], day)

    def test_rents_after_departure_are_dropped(self):
        self.lease.auto_schedules = True
        self.lease.save()
        before, after = self.add_schedule(days=-20), self.add_schedule(days=-2)
        self.end("complete", ended_on=(self.today - timedelta(days=5)).isoformat())
        self.assertTrue(PaymentSchedule.objects.filter(pk=before.pk).exists())
        self.assertFalse(PaymentSchedule.objects.filter(pk=after.pk).exists())


class InspectionTests(MoveOutCase):
    def create(self, kind="ENTRY", expect=201, **body):
        response = self.api_a.post(self.url("inspections/"), {"kind": kind, **body}, format="json")
        self.assertEqual(response.status_code, expect, response.content)
        return response.json()

    def fill(self, inspection, condition="GOOD"):
        for item in inspection["items"]:
            self.api_a.patch(f"/api/v1/inspections/items/{item['id']}/", {"condition": condition}, format="json")

    def sign(self, inspection, expect=200, **body):
        response = self.api_a.post(f"/api/v1/inspections/{inspection['id']}/sign/", {"tenant_signer": "Ibrahima Sarr", **body}, format="json")
        self.assertEqual(response.status_code, expect, response.content)
        return response.json()

    def entry(self):
        inspection = self.create()
        self.fill(inspection)
        self.sign(inspection)
        return inspection

    def test_rooms_follow_the_unit(self):
        def rooms(**fields):
            return [room for room, _ in default_rooms(make_unit(self.org_a, **fields))]

        self.assertEqual(rooms(bedrooms=2, bathrooms=2), ["Entrée et séjour", "Cuisine", "Chambre 1", "Chambre 2", "Salle de bain 1", "Salle de bain 2"])
        self.assertEqual(rooms(unit_type="F3"), ["Entrée et séjour", "Cuisine", "Chambre 1", "Chambre 2", "Salle de bain"])
        self.assertEqual(rooms(category="STUDIO", unit_type="Studio"), ["Pièce principale", "Cuisine", "Salle de bain"])
        self.assertEqual(rooms(category="LAND"), ["Terrain"])
        self.assertIn("Mobilier", rooms(is_furnished=True))

    def test_lifecycle(self):
        inspection = self.create()
        self.assertEqual((inspection["status"], inspection["unit_label"]), ("DRAFT", self.unit.label))
        self.assertIn("à regarder", self.sign(inspection, expect=400)["detail"])
        self.fill(inspection)
        self.api_a.patch(f"/api/v1/inspections/{inspection['id']}/", {"electricity_reading": "01542", "keys_count": 3}, format="json")
        signed = self.sign(inspection, tenant_remarks="La porte grince")
        self.assertEqual((signed["status"], signed["tenant_signer"], signed["keys_count"]), ("SIGNED", "Ibrahima Sarr", 3))
        # Validé : plus rien ne bouge.
        item = signed["items"][0]["id"]
        self.assertEqual(self.api_a.patch(f"/api/v1/inspections/items/{item}/", {"condition": "DAMAGED"}, format="json").status_code, 400)
        self.assertEqual(self.api_a.patch(f"/api/v1/inspections/{inspection['id']}/", {"note": "x"}, format="json").status_code, 400)
        self.assertEqual(self.api_a.delete(f"/api/v1/inspections/{inspection['id']}/").status_code, 400)
        self.assertEqual(self.api_a.post(f"/api/v1/inspections/{inspection['id']}/reopen/").json()["status"], "DRAFT")

    def test_one_per_kind_and_status(self):
        self.create()
        self.create(expect=400)
        draft = make_lease(self.org_a, unit=make_unit(self.org_a))
        self.assertEqual(self.api_a.post(self.url("inspections/", draft), {"kind": "EXIT"}).status_code, 400)
        self.end()
        Inspection.objects.all().delete()
        self.create(expect=400)

    def test_exit_compares_with_entry(self):
        entry = self.entry()
        exit_ = self.create("EXIT")
        self.assertEqual([i["label"] for i in exit_["items"]], [i["label"] for i in entry["items"]])
        self.assertEqual({i["entry_condition"] for i in exit_["items"]}, {"GOOD"})
        self.assertEqual({i["condition"] for i in exit_["items"]}, {""})
        self.fill(exit_)
        item = exit_["items"][3]
        self.api_a.patch(f"/api/v1/inspections/items/{item['id']}/", {"condition": "DAMAGED", "note": "Prise arrachée"}, format="json")
        # Une usure normale ne se reproche pas au locataire ; un brouillon ne compte pas encore.
        self.api_a.patch(f"/api/v1/inspections/items/{exit_['items'][0]['id']}/", {"condition": "WORN"}, format="json")
        self.assertEqual(self.deposit()["faults"], [])
        self.sign(exit_)
        self.assertEqual([(f["label"], f["note"]) for f in self.deposit()["faults"]], [(item["label"], "Prise arrachée")])
        # L'entrée sert de base : elle ne se rouvre plus.
        self.assertEqual(self.api_a.post(f"/api/v1/inspections/{entry['id']}/reopen/").status_code, 400)

    def test_damage_already_there_is_not_a_fault(self):
        inspection = self.create()
        self.fill(inspection, "DAMAGED")
        self.sign(inspection)
        exit_ = self.create("EXIT")
        self.fill(exit_, "DAMAGED")
        self.sign(exit_)
        self.assertEqual(self.deposit()["faults"], [])

    def test_added_item_stays_in_its_room(self):
        inspection = self.create()
        response = self.api_a.post(f"/api/v1/inspections/{inspection['id']}/items/", {"room": "Cuisine", "label": "Hotte"}, format="json")
        self.assertEqual(response.status_code, 201)
        self.api_a.post(f"/api/v1/inspections/{inspection['id']}/items/", {"room": "Balcon", "label": "Garde-corps"}, format="json")
        items = self.api_a.get(f"/api/v1/inspections/{inspection['id']}/").json()["items"]
        kitchen = [i["label"] for i in items if i["room"] == "Cuisine"]
        self.assertEqual(kitchen[-1], "Hotte")
        order = [i["room"] for i in items]
        self.assertEqual(len([1 for a, b in zip(order, order[1:]) if a != b]) + 1, len(set(order)))
        self.assertEqual(items[-1]["label"], "Garde-corps")
        self.assertEqual(self.api_a.delete(f"/api/v1/inspections/items/{items[-1]['id']}/").status_code, 204)

    def test_isolation_and_rights(self):
        inspection = self.create()
        item = inspection["items"][0]["id"]
        for response in (
            self.api_b.get(f"/api/v1/inspections/{inspection['id']}/"),
            self.api_b.patch(f"/api/v1/inspections/items/{item}/", {"condition": "GOOD"}, format="json"),
            self.api_b.post(f"/api/v1/inspections/{inspection['id']}/sign/", {"tenant_signer": "x"}),
            self.api_b.get(f"/api/v1/inspections/{inspection['id']}/pdf/"),
            self.api_b.get(self.url("inspections/")),
            self.api_b.get(self.url("deposit/")),
        ):
            self.assertEqual(response.status_code, 404)
        viewer = client_for(add_member(self.org_a, role="VIEWER"))
        self.assertEqual(viewer.get(f"/api/v1/inspections/{inspection['id']}/").status_code, 200)
        self.assertEqual(viewer.post(self.url("inspections/"), {"kind": "EXIT"}).status_code, 403)
        # Le comptable règle la caution mais ne fait pas l'état des lieux.
        accountant = client_for(add_member(self.org_a, role="ACCOUNTANT"))
        self.assertEqual(accountant.patch(f"/api/v1/inspections/items/{item}/", {"condition": "GOOD"}, format="json").status_code, 403)

    def test_summary(self):
        inspection = self.create()
        self.api_a.patch(f"/api/v1/inspections/items/{inspection['items'][0]['id']}/", {"condition": "GOOD"}, format="json")
        row = self.api_a.get(self.url("inspections/")).json()[0]
        self.assertEqual((row["done_count"], row["items_count"], row["photos_count"]), (1, len(inspection["items"]), 0))

    def test_report(self):
        entry = self.entry()
        response = self.api_a.get(f"/api/v1/inspections/{entry['id']}/pdf/")
        self.assertTrue(response.content.startswith(b"%PDF"))
        share = self.api_a.get(f"/api/v1/inspections/{entry['id']}/share/").json()
        token = share["url"].rsplit("/", 1)[1]
        self.assertEqual(self.client.get(f"/api/v1/documents/{token}/").status_code, 200)
        # Rouvert pour correction : le lien déjà envoyé ne montre pas un document en cours.
        self.api_a.post(f"/api/v1/inspections/{entry['id']}/reopen/")
        self.assertEqual(self.client.get(f"/api/v1/documents/{token}/").status_code, 404)
        self.assertEqual(self.api_a.get(f"/api/v1/inspections/{entry['id']}/share/").status_code, 400)


class PhotoTests(MoveOutCase):
    def setUp(self):
        super().setUp()
        self.inspection = self.api_a.post(self.url("inspections/"), {"kind": "ENTRY"}).json()

    def upload(self, file=None, expect=201, client=None, **fields):
        response = (client or self.api_a).post(
            f"/api/v1/inspections/{self.inspection['id']}/photos/", {"image": file or image_file(), **fields}, format="multipart"
        )
        self.assertEqual(response.status_code, expect, response.content)
        return response.json()

    def test_upload_read_and_delete(self):
        item = self.inspection["items"][0]["id"]
        photo = self.upload(item=item)
        self.assertEqual(photo["item"], item)
        # Lisible par le lien signé, sans compte ni agence active.
        response = self.client.get(photo["path"])
        self.assertEqual((response.status_code, response["Content-Type"]), (200, "image/jpeg"))
        self.assertIn("private", response["Cache-Control"])
        self.assertTrue(b"".join(response.streaming_content).startswith(bytes([255, 216])))
        path = Path(InspectionPhoto.objects.get().image.path)
        self.assertTrue(path.exists())
        self.assertTrue(str(path).startswith(str(Path(self.private))))
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.api_a.delete(f"/api/v1/inspections/photos/{photo['id']}/").status_code, 204)
        self.assertFalse(path.exists())
        self.assertEqual(self.client.get(photo["path"]).status_code, 404)

    def test_link_is_signed_and_expires(self):
        photo = self.upload()
        self.assertEqual(self.client.get(photo["path"][:-4] + "xx/").status_code, 404)
        self.assertEqual(self.client.get("/api/v1/inspections/photos/file/1/").status_code, 404)
        stored = InspectionPhoto.objects.get()
        with override_settings():
            from unittest import mock

            with mock.patch("inspections.photos.timezone.localdate", return_value=self.today - timedelta(days=2)):
                old = photo_path(stored)
        self.assertEqual(self.client.get(old).status_code, 404)

    def test_photos_are_shrunk_and_stripped(self):
        buffer = BytesIO()
        exif = Image.Exif()
        exif[0x010F] = "Téléphone"
        Image.new("RGB", (3000, 2000), (10, 120, 200)).save(buffer, format="JPEG", exif=exif)
        self.upload(SimpleUploadedFile("p.jpg", buffer.getvalue(), content_type="image/jpeg"))
        with InspectionPhoto.objects.get().image.open() as file:
            image = Image.open(file)
            self.assertEqual((image.format, max(image.size)), ("JPEG", 1600))
            self.assertFalse(dict(image.getexif()))

    def test_refusals(self):
        self.assertIn("image", self.upload(image_file(name="a.gif", image_format="GIF"), expect=400))
        self.assertIn("image", self.upload(SimpleUploadedFile("a.png", b"pas une image", content_type="image/png"), expect=400))
        self.upload(expect=404, item=999999)
        self.upload(expect=404, client=self.api_b)

    def test_deleting_the_inspection_removes_files(self):
        self.upload()
        path = Path(InspectionPhoto.objects.get().image.path)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.api_a.delete(f"/api/v1/inspections/{self.inspection['id']}/").status_code, 204)
        self.assertFalse(path.exists())

    def test_report_with_photos(self):
        self.upload(item=self.inspection["items"][0]["id"])
        self.upload()
        self.assertEqual(self.api_a.get(f"/api/v1/inspections/{self.inspection['id']}/pdf/").status_code, 200)
        # Un fichier perdu n'empêche pas d'émettre le document.
        Path(InspectionPhoto.objects.first().image.path).unlink()
        self.assertEqual(self.api_a.get(f"/api/v1/inspections/{self.inspection['id']}/pdf/").status_code, 200)


class DepositStateTests(MoveOutCase):
    def test_states(self):
        # Bail repris : la caution inscrite est réputée détenue, à confirmer.
        self.assertEqual((self.deposit()["state"], self.deposit()["declared"]), ("HELD", True))
        schedule = self.add_schedule("DEPOSIT", 300000)
        self.assertEqual((self.deposit()["state"], self.deposit()["held"]), ("EXPECTED", "0.00"))
        schedule.delete()
        self.pay_deposit()
        self.assertEqual((self.deposit()["state"], self.deposit()["held"], self.deposit()["declared"]), ("HELD", "300000.00", False))
        self.end()
        self.assertEqual(self.deposit()["state"], "TO_RETURN")
        self.settle()
        self.assertEqual(self.deposit()["state"], "SETTLED")

    def test_never_paid_deposit_is_not_to_return(self):
        self.add_schedule("DEPOSIT", 300000)
        self.end()
        self.assertEqual((self.deposit()["state"], self.deposit()["held"]), ("NONE", "0.00"))
        self.settle(expect=400)
        self.assertEqual(build_deposits(self.org_a)["rows"], [])

    def test_board_and_digest(self):
        self.pay_deposit()
        data = self.api_a.get("/api/v1/deposits/").json()
        self.assertEqual((data["held"], data["held_count"], data["to_return"]), ("300000.00", 1, "0.00"))
        self.end()
        data = self.api_a.get("/api/v1/deposits/").json()
        self.assertEqual((data["to_return"], data["to_return_count"], data["rows"][0]["state"]), ("300000.00", 1, "TO_RETURN"))
        titles = [section["title"] for section in build_digest(self.org_a, {"deposit.view"}, today=self.today)]
        self.assertTrue(titles[0].startswith("Cautions à rendre"))
        self.assertEqual(self.api_b.get("/api/v1/deposits/").json()["rows"], [])
        self.settle()
        data = self.api_a.get("/api/v1/deposits/").json()
        self.assertEqual((data["held"], data["rows"][0]["state"], data["rows"][0]["refunded"]), ("0.00", "SETTLED", "300000.00"))

    def test_board_query_count_does_not_grow(self):
        def count():
            from django.db import connection
            from django.test.utils import CaptureQueriesContext

            with CaptureQueriesContext(connection, ) as queries:
                build_deposits(self.org_a)
            return len(queries)

        first = count()
        for _ in range(3):
            lease = make_lease(self.org_a, status="ACTIVE")
            lease.deposit_amount = 1000
            lease.save()
        self.assertEqual(count(), first)


class SettlementTests(MoveOutCase):
    def test_full_refund(self):
        self.pay_deposit()
        self.end()
        data = self.settle(reference="VIR-1")
        self.assertEqual((data["refund_amount"], data["method_label"], data["reference"]), ("300000.00", "Wave", "VIR-1"))
        # L'argent rendu n'est ni un paiement ni une dépense du bailleur.
        self.assertEqual(Payment.objects.count(), 1)
        self.assertNotIn(self.owner.pk, {k for k, v in owner_balances(self.org_a).items() if v["balance"]})

    def test_rents_and_repairs_are_retained(self):
        self.pay_deposit()
        october, november = self.add_schedule(days=-40), self.add_schedule(amount=100000, days=-10)
        self.end()
        summary = self.deposit()
        self.assertEqual((summary["unpaid"], summary["unpaid_count"]), ("250000.00", 2))
        data = self.settle(retain_unpaid="200000", deductions=[{"kind": "REPAIR", "label": "Évier", "amount": "40000"}])
        self.assertEqual((data["retained_unpaid"], data["refund_amount"]), ("200000.00", "60000.00"))
        # Les loyers les plus anciens d'abord ; le reste demeure dû.
        october.refresh_from_db(), november.refresh_from_db()
        self.assertEqual((october.is_paid, november.is_paid), (True, False))
        row = build_rent_roll(self.org_a, month=self.today)["rows"][0]
        self.assertEqual(row["total_due"], 50000)
        # Bailleur : loyers moins 10 %, plus la réparation retenue, sans commission.
        balance = owner_balances(self.org_a)[self.owner.pk]
        self.assertEqual((balance["collected"], balance["commission"], balance["retentions"], balance["balance"]), (200000, 20000, 40000, 220000))
        statement = build_statement(self.owner, month=self.today)
        self.assertEqual((statement["retentions"], statement["retention_lines"][0]["label"]), (40000, "Réparation : Évier"))
        self.assertEqual(statement["closing_balance"], 220000)
        self.assertEqual(self.api_a.get(f"/api/v1/owners/{self.owner.pk}/statement/pdf/").status_code, 200)

    def test_retention_is_not_new_cash(self):
        self.pay_deposit()
        self.add_schedule()
        self.end()
        InAppNotification.objects.all().delete()
        with self.captureOnCommitCallbacks(execute=True):
            self.settle(retain_unpaid="150000")
        self.assertEqual([p.amount_paid for p in Payment.objects.cash()], [300000])
        self.assertEqual(Payment.objects.valid().count(), 2)
        self.assertFalse(InAppNotification.objects.filter(kind="PAYMENT_RECEIVED").exists())
        dashboard = self.api_a.get("/api/v1/analytics/dashboard/").json()
        self.assertEqual(Decimal(dashboard["finance"]["monthly"][-1]["collected"]), 300000)

    def test_retention_method_is_reserved(self):
        self.pay_deposit()
        self.add_schedule()
        self.end()
        self.settle(retain_unpaid="150000")
        method = PaymentMethod.objects.get(code="DEPOSIT")
        self.assertNotIn("DEPOSIT", [m["code"] for m in self.api_a.get("/api/v1/payments/methods/").json()])
        body = {"lease": self.lease.pk, "amount": "1000", "payment_method": method.pk}
        self.assertEqual(self.api_a.post("/api/v1/payments/collect/", body).status_code, 400)
        body = {"payer": self.lease.tenant_id, "amount_paid": "1000", "payment_method": method.pk}
        self.assertEqual(self.api_a.post("/api/v1/payments/payments/", body).status_code, 400)
        payment = Payment.objects.get(payment_method=method)
        response = self.api_a.post(f"/api/v1/payments/payments/{payment.pk}/cancel/", {"reason": "x"})
        self.assertIn("décompte", response.json()["detail"])
        listed = self.api_a.get("/api/v1/payments/payments/").json()["results"]
        self.assertIn("Retenue sur caution", [p["payment_method_label"] for p in listed])

    def test_cannot_retain_more(self):
        self.pay_deposit()
        self.add_schedule()
        self.end()
        self.assertIn("retain_unpaid", self.settle(expect=400, retain_unpaid="150001"))
        self.assertIn("deductions", self.settle(expect=400, deductions=[{"kind": "REPAIR", "label": "Tout", "amount": "300001"}]))
        self.assertIn("deductions", self.settle(expect=400, retain_unpaid="150000", deductions=[{"kind": "OTHER", "label": "x", "amount": "150001"}]))
        self.assertFalse(DepositSettlement.objects.exists())

    def test_everything_retained_needs_no_method(self):
        self.pay_deposit()
        self.end()
        data = self.settle(method=None, deductions=[{"kind": "REPAIR", "label": "Peinture", "amount": "300000"}])
        self.assertEqual((data["refund_amount"], data["method_label"]), ("0.00", ""))
        self.assertEqual(self.api_a.get(f"/api/v1/deposits/settlements/{data['id']}/pdf/").status_code, 200)

    def test_guards(self):
        self.pay_deposit()
        self.settle(expect=400)  # bail encore actif
        self.end()
        self.assertIn("method", self.settle(expect=400, method=None))
        self.assertIn("settled_on", self.settle(expect=400, settled_on=(self.today + timedelta(days=1)).isoformat()))
        self.assertIn("held", self.settle(expect=400, held="500000"))
        self.settle()
        self.assertIn("déjà réglée", self.settle(expect=400)["detail"])
        viewer = client_for(add_member(self.org_a, role="VIEWER"))
        self.assertEqual(viewer.post(self.url("deposit/settle/"), {}).status_code, 403)
        accountant = client_for(add_member(self.org_a, role="ACCOUNTANT"))
        self.assertEqual(accountant.get(self.url("deposit/")).status_code, 200)

    def test_declared_deposit_is_confirmed(self):
        self.end()
        self.assertEqual((self.deposit()["declared"], self.deposit()["state"]), (True, "TO_RETURN"))
        self.assertEqual(self.settle(held="250000")["refund_amount"], "250000.00")

    def test_declared_deposit_never_received(self):
        self.end()
        data = self.settle(held="0", method=None)
        self.assertEqual((data["held_amount"], data["refund_amount"]), ("0.00", "0.00"))
        self.assertEqual(self.deposit()["state"], "SETTLED")

    def test_partly_paid_deposit(self):
        schedule = self.pay_deposit(amount=200000)
        self.end()
        self.assertEqual((self.deposit()["held"], self.deposit()["unpaid"]), ("200000.00", "0.00"))
        data = self.settle()
        schedule.refresh_from_db()
        self.assertEqual((schedule.amount_due, schedule.is_paid), (200000, True))
        self.api_a.post(f"/api/v1/deposits/settlements/{data['id']}/cancel/", {"reason": "Erreur"})
        schedule.refresh_from_db()
        self.assertEqual((schedule.amount_due, schedule.is_paid), (300000, False))

    def test_cancel_restores_everything(self):
        self.pay_deposit()
        rent = self.add_schedule()
        self.end()
        data = self.settle(retain_unpaid="150000", deductions=[{"kind": "REPAIR", "label": "Évier", "amount": "20000"}])
        url = f"/api/v1/deposits/settlements/{data['id']}/cancel/"
        self.assertEqual(self.api_b.post(url, {"reason": "x"}).status_code, 404)
        self.assertEqual(self.api_a.post(url, {"reason": ""}).status_code, 400)
        self.assertIsNotNone(self.api_a.post(url, {"reason": "Mauvais montant"}).json()["cancelled_at"])
        self.assertEqual(self.api_a.post(url, {"reason": "Encore"}).status_code, 400)
        rent.refresh_from_db()
        self.assertFalse(rent.is_paid)
        self.assertEqual(self.deposit()["state"], "TO_RETURN")
        self.assertEqual(owner_balances(self.org_a).get(self.owner.pk, {}).get("balance", 0), 0)
        self.settle()  # on peut refaire le décompte

    def test_settled_exit_inspection_cannot_reopen(self):
        self.pay_deposit()
        inspection = self.api_a.post(self.url("inspections/"), {"kind": "EXIT"}).json()
        for item in inspection["items"]:
            self.api_a.patch(f"/api/v1/inspections/items/{item['id']}/", {"condition": "GOOD"}, format="json")
        self.api_a.post(f"/api/v1/inspections/{inspection['id']}/sign/", {"tenant_signer": "x"})
        self.end()
        self.settle()
        self.assertEqual(self.api_a.post(f"/api/v1/inspections/{inspection['id']}/reopen/").status_code, 400)

    def test_documents(self):
        self.pay_deposit()
        self.add_schedule()
        self.end()
        data = self.settle(retain_unpaid="150000", deductions=[{"kind": "KEYS", "label": "Badge <portail> & clé", "amount": "5000"}], note="Remis en main propre")
        path = f"/api/v1/deposits/settlements/{data['id']}/"
        self.assertTrue(self.api_a.get(f"{path}pdf/").content.startswith(b"%PDF"))
        self.assertEqual(self.api_b.get(f"{path}pdf/").status_code, 404)
        token = self.api_a.get(f"{path}share/").json()["url"].rsplit("/", 1)[1]
        self.assertEqual(self.client.get(f"/api/v1/documents/{token}/").status_code, 200)
        self.api_a.post(f"{path}cancel/", {"reason": "Erreur"})
        self.assertEqual(self.client.get(f"/api/v1/documents/{token}/").status_code, 404)

    def test_email_needs_an_address(self):
        self.pay_deposit()
        self.end()
        path = f"/api/v1/deposits/settlements/{self.settle()['id']}/email/"
        self.assertEqual(self.api_a.post(path).status_code, 400)
        self.lease.tenant.tenant_profiles.filter(organization=self.org_a).update(email="locataire@gmail.com")
        self.assertEqual(self.api_a.post(path).status_code, 204)

    def test_old_leases_have_no_departure_date(self):
        LeaseContract.objects.filter(pk=self.lease.pk).update(status="COMPLETED", ended_on=None)
        self.assertEqual(self.deposit()["state"], "TO_RETURN")
        self.assertEqual(self.api_a.get(f"/api/v1/deposits/settlements/{self.settle()['id']}/pdf/").status_code, 200)
