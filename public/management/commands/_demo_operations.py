"""
Données de gestion de l'agence de démonstration Teranga : référentiels, locataires, baux actifs,
échéances, paiements (un locataire à jour, une locataire en retard) et un ticket de maintenance.
Appelé par la commande seed_demo ; idempotent.
"""

from datetime import date, datetime, time
from decimal import Decimal

from django.utils import timezone

from maintenance.models import MaintenanceAssignment, MaintenanceCategory, MaintenanceLog, MaintenanceTicket
from leases.models import LeaseContract, Tenant
from leases.services import change_lease_status
from leases.tenants import register_tenant
from payments.models import Payment, PaymentMethod, PaymentSchedule
from payments.services import allocate_payment
from properties.models import Building, Property, Unit

PAYMENT_METHODS = [
    ("WAVE", "Wave"),
    ("ORANGE_MONEY", "Orange Money"),
    ("FREE_MONEY", "Free Money"),
    ("CASH", "Espèces"),
    ("BANK_TRANSFER", "Virement bancaire"),
]

MAINTENANCE_CATEGORIES = [
    ("PLUMBING", "Plomberie"),
    ("ELECTRICITY", "Électricité"),
    ("AIR_CONDITIONING", "Climatisation"),
    ("PAINTING", "Peinture"),
    ("LOCKSMITH", "Serrurerie"),
    ("CLEANING", "Nettoyage"),
]

# (lot, catégorie, surface, chambres, téléphone du locataire, prénom, nom, loyer, charges, mois écoulés, mois payés, moyen)
RENTALS = [
    ("B101", "APARTMENT", 70, 2, "+221771112233", "Moussa", "Ndiaye", "400000", "25000", 3, 4, "WAVE"),
    ("B102", "STUDIO", 35, 1, "+221776543210", "Aïssatou", "Sarr", "200000", "10000", 2, 1, "ORANGE_MONEY"),
]


def month_start(today, months_back):
    month = today.month - months_back
    year = today.year + (month - 1) // 12
    return date(year, (month - 1) % 12 + 1, 1)


def seed_reference_data():
    for code, label in PAYMENT_METHODS:
        PaymentMethod.objects.get_or_create(code=code, defaults={"label": label})
    for code, label in MAINTENANCE_CATEGORIES:
        MaintenanceCategory.objects.get_or_create(code=code, defaults={"label": label})


def seed_operations(organization, admin):
    """Baux, échéances, paiements et ticket pour l'agence ; ne fait rien si déjà présents."""
    prop = Property.objects.get(organization=organization, name="Résidence Les Almadies")
    building, _ = Building.objects.get_or_create(property=prop, name="Bâtiment principal")
    today = date.today()

    for reference, category, surface, bedrooms, phone, first, last, rent, charges, months, paid, method in RENTALS:
        unit, _ = Unit.objects.get_or_create(
            building=building,
            reference=reference,
            defaults={"category": category, "unit_type": dict(Unit.CATEGORY_CHOICES)[category], "surface": surface,
                      "bedrooms": bedrooms, "bathrooms": 1, "status": "FREE"},
        )
        if LeaseContract.objects.filter(unit=unit).exists():
            continue

        tenant = Tenant.objects.filter(organization=organization, user__phone=phone).first()
        tenant_user = tenant.user if tenant else register_tenant(organization, phone=phone, first_name=first, last_name=last).user

        start = month_start(today, months)
        lease = LeaseContract.objects.create(
            organization=organization, unit=unit, tenant=tenant_user, created_by=admin, start_date=start,
            rent_amount=Decimal(rent), charges_amount=Decimal(charges), deposit_amount=Decimal(rent) * 2,
        )
        change_lease_status(lease, "ACTIVE")

        # Une échéance par mois (le 5), du début du bail au mois courant.
        schedules = [
            PaymentSchedule.objects.create(
                organization=organization, lease_contract=lease, schedule_type="RENT",
                due_date=month_start(today, back).replace(day=5), amount_due=Decimal(rent) + Decimal(charges),
            )
            for back in range(months, -1, -1)
        ]
        for index, schedule in enumerate(schedules[:paid]):
            payment = Payment.objects.create(
                organization=organization, payer=tenant_user, recorded_by=admin, amount_paid=schedule.amount_due,
                payment_method=PaymentMethod.objects.get(code=method), reference=f"DEMO-{reference}-{index + 1:02d}",
                note="Loyer et charges",
            )
            paid_on = timezone.make_aware(datetime.combine(schedule.due_date.replace(day=3), time(10)))
            Payment.objects.filter(pk=payment.pk).update(payment_date=paid_on)
            allocate_payment(payment, [{"schedule": schedule, "amount": schedule.amount_due}])

    first_unit = Unit.objects.get(building=building, reference=RENTALS[0][0])
    if not MaintenanceTicket.objects.filter(unit=first_unit).exists():
        ticket = MaintenanceTicket.objects.create(
            unit=first_unit, reported_by=admin, priority="HIGH", status="IN_PROGRESS",
            category=MaintenanceCategory.objects.get(code="PLUMBING"),
            description="Fuite sous l'évier de la cuisine signalée par le locataire, l'eau coule dans le placard.",
        )
        MaintenanceAssignment.objects.create(ticket=ticket, assigned_to=admin, assigned_by=admin)
        MaintenanceLog.objects.create(ticket=ticket, user=admin, message="Appel du locataire, plombier contacté.")
        MaintenanceLog.objects.create(ticket=ticket, user=admin, message="Passage du plombier prévu demain matin.")
