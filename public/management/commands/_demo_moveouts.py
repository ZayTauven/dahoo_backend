"""
Démonstration des entrées et sorties : un état des lieux d'entrée, une sortie en cours de saisie, un départ
dont la caution attend, un départ déjà réglé. Idempotent (repéré par le téléphone du locataire).
"""

from datetime import datetime, time, timedelta
from decimal import Decimal
from itertools import cycle
from pathlib import Path

from django.core.files.base import File
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from deposits.services import settle_deposit
from inspections.models import InspectionPhoto
from inspections.photos import prepare
from inspections.services import create_inspection, sign_inspection
from leases.models import LeaseContract
from leases.services import change_lease_status
from leases.tenants import register_tenant
from payments.models import Payment, PaymentMethod, PaymentSchedule
from payments.services import allocate_payment
from properties.models import Building, Unit

from ._demo_operations import month_start

# (lot, téléphone, prénom, nom, loyer, caution, entré il y a (mois), parti il y a (jours), dernier loyer impayé)
DEPARTURES = [
    ("M14", "+221775550301", "Boubacar", "Sy", 310000, 620000, 14, 6, True),
    ("M15", "+221775550302", "Rama", "Cissé", 260000, 520000, 20, 34, False),
]
# Dégradations relevées à la sortie du premier : (pièce, élément) → (état, observation)
FAULTS = {
    ("Cuisine", "Évier et robinetterie"): ("DAMAGED", "Mitigeur cassé, fuite sous l'évier"),
    ("Chambre 1", "Portes et fenêtres"): ("DAMAGED", "Vitre fêlée"),
    ("Entrée et séjour", "Murs et plafond"): ("WORN", "Traces d'usage, à rafraîchir"),
}


def _aware(day):
    return timezone.make_aware(datetime.combine(day, time(11)))


def _pay(lease, admin, schedule, day):
    payment = Payment.objects.create(
        organization=lease.organization, payer=lease.tenant, recorded_by=admin, amount_paid=schedule.amount_due,
        payment_method=PaymentMethod.objects.get(code="WAVE"), payment_date=_aware(day),
    )
    allocate_payment(payment, [{"schedule": schedule, "amount": schedule.amount_due}])


def _photos(inspection, sources, rooms):
    """Une photo par pièce citée, prise dans les visuels de démonstration (réduite comme un envoi réel)."""
    for room in rooms:
        source = next(sources, None)
        item = inspection.items.filter(room=room).first()
        if source is None or item is None:
            continue
        with source.open("rb") as handle:
            upload = SimpleUploadedFile(source.name, File(handle).read(), content_type="image/webp")
        InspectionPhoto.objects.create(inspection=inspection, item=item, image=prepare(upload))


def _fill(inspection, *, day, faults=None, only=None, readings=("01542", "0318"), keys=2):
    for index, item in enumerate(inspection.items.all()):
        if only is not None and index >= only:
            break
        item.condition, item.note = (faults or {}).get((item.room, item.label), ("GOOD", ""))
        item.save(update_fields=["condition", "note"])
    inspection.done_on, inspection.keys_count = day, keys
    inspection.electricity_reading, inspection.water_reading = readings
    inspection.save()


def _departed(organization, admin, building, spec, today, sources):
    reference, phone, first, last, rent, deposit, months, days_ago, unpaid = spec
    unit, _ = Unit.objects.get_or_create(building=building, reference=reference, defaults={
        "category": "APARTMENT", "unit_type": "T3", "surface": 78, "bedrooms": 2, "bathrooms": 1, "status": "FREE",
    })
    tenant = register_tenant(organization, phone=phone, first_name=first, last_name=last).user
    start, left = month_start(today, months), today - timedelta(days=days_ago)
    lease = LeaseContract.objects.create(
        organization=organization, unit=unit, tenant=tenant, created_by=admin, start_date=start,
        rent_amount=Decimal(rent), deposit_amount=Decimal(deposit), due_day=5,
    )
    lease = change_lease_status(lease, "ACTIVE")
    LeaseContract.objects.filter(pk=lease.pk).update(signed_at=_aware(start), created_at=_aware(start))
    caution = PaymentSchedule.objects.create(organization=organization, lease_contract=lease, schedule_type="DEPOSIT", due_date=start, amount_due=deposit)
    _pay(lease, admin, caution, start)
    due = [month_start(left, back).replace(day=5) for back in (2, 1, 0)]
    due = [day for day in due if day <= left]
    for day in due:
        schedule = PaymentSchedule.objects.create(organization=organization, lease_contract=lease, schedule_type="RENT", due_date=day, amount_due=rent)
        if not (unpaid and day == due[-1]):
            _pay(lease, admin, schedule, day)

    entry = create_inspection(lease, kind="ENTRY", user=admin)
    _fill(entry, day=start, keys=3)
    _photos(entry, sources, ["Entrée et séjour", "Cuisine"])
    sign_inspection(entry, user=admin, tenant_signer=f"{first} {last}")
    exit_ = create_inspection(lease, kind="EXIT", user=admin)
    _fill(exit_, day=left, faults=FAULTS if unpaid else None, readings=("04879", "0902"), keys=2 if unpaid else 3)
    _photos(exit_, sources, ["Cuisine", "Chambre 1"] if unpaid else ["Cuisine"])
    sign_inspection(exit_, user=admin, tenant_signer=f"{first} {last}", tenant_remarks="Le mitigeur fuyait déjà en octobre." if unpaid else "")
    lease = change_lease_status(lease, "TERMINATED", ended_on=left)
    if not unpaid:
        settle_deposit(
            lease, user=admin, deductions=[{"kind": "UTILITIES", "label": "Dernière facture d'eau", "amount": Decimal("14500")}],
            method=PaymentMethod.objects.get(code="WAVE"), reference="WV-88214", settled_on=left + timedelta(days=9),
        )
        change_lease_status(lease, "COMPLETED")


def seed_moveouts(organization, admin, photos):
    today = timezone.localdate()
    sources = cycle(sorted(Path(photos).glob("interieur-*.webp")))
    building = Building.objects.filter(property__organization=organization, units__reference="M01").first()
    if building is None:
        return
    for spec in DEPARTURES:
        if not LeaseContract.objects.filter(organization=organization, tenant__phone=spec[1]).exists():
            _departed(organization, admin, building, spec, today, sources)

    def lease_of(reference):
        return LeaseContract.objects.filter(organization=organization, unit__reference=reference, status="ACTIVE").first()

    # Entrée validée, bail en cours.
    lease = lease_of("M01")
    if lease and not lease.inspections.exists():
        entry = create_inspection(lease, kind="ENTRY", user=admin)
        _fill(entry, day=lease.start_date, keys=4)
        _photos(entry, sources, ["Entrée et séjour", "Cuisine", "Chambre 1"])
        sign_inspection(entry, user=admin, tenant_signer=f"{lease.tenant.first_name} {lease.tenant.last_name}")
    # Bail arrivé à son terme : sortie en cours de saisie, à terminer soi-même.
    lease = lease_of("M02")
    if lease and not lease.inspections.exists():
        entry = create_inspection(lease, kind="ENTRY", user=admin)
        _fill(entry, day=lease.start_date)
        sign_inspection(entry, user=admin, tenant_signer=f"{lease.tenant.first_name} {lease.tenant.last_name}")
        _fill(create_inspection(lease, kind="EXIT", user=admin), day=today, only=6, readings=("03310", "0677"))
