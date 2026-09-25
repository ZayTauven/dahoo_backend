"""
Historique de 12 mois pour l'agence de démonstration Teranga : de quoi alimenter le tableau de bord
(encaissements, retards, occupation, maintenance, demandes de visite). Appelé par seed_demo ;
déterministe (graine fixe) et idempotent (ne fait rien si la résidence existe déjà).

Profils de paiement : « ponctuel » (paie avant le 5), « tardif » (1 à 3 semaines de retard),
« irrégulier » (paiements partiels, deux mois sautés), « en retard » (les trois derniers mois impayés).
"""

import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.utils import timezone

from leases.models import LeaseContract
from leases.services import change_lease_status
from leases.tenants import register_tenant
from listings.models import Listing, Prospect, ProspectInterest
from maintenance.models import MaintenanceCategory, MaintenanceLog, MaintenanceTicket
from payments.models import Payment, PaymentMethod, PaymentSchedule
from payments.services import allocate_payment
from properties.models import Building, Property, Unit

from ._demo_operations import month_start

HISTORY_PROPERTY = ("Résidence Teranga Mermoz", "Rue 10, Mermoz", "Mermoz", "Dakar", "14.707300", "-17.475800")

# (lot, catégorie, surface, chambres, téléphone, prénom, nom, loyer, charges, début (mois), fin (jours), profil, moyen)
HISTORY_RENTALS = [
    ("M01", "APARTMENT", 85, 3, "+221775550101", "Mamadou", "Diallo", "450000", "30000", 14, None, "ponctuel", "WAVE"),
    ("M02", "APARTMENT", 72, 2, "+221775550102", "Fatou", "Sow", "380000", "25000", 13, 38, "ponctuel", "ORANGE_MONEY"),
    ("M03", "STUDIO", 32, 1, "+221775550103", "Cheikh", "Mbaye", "190000", "10000", 12, None, "tardif", "WAVE"),
    ("M04", "APARTMENT", 110, 3, "+221775550104", "Awa", "Ndoye", "650000", "40000", 11, 82, "ponctuel", "BANK_TRANSFER"),
    ("M05", "STUDIO", 35, 1, "+221775550105", "Ousmane", "Faye", "210000", "10000", 9, None, "irregulier", "CASH"),
    ("M06", "APARTMENT", 68, 2, "+221775550106", "Mariama", "Cissé", "360000", "25000", 8, None, "tardif", "ORANGE_MONEY"),
    ("M07", "APARTMENT", 90, 3, "+221775550107", "Ibrahima", "Kane", "520000", "30000", 6, None, "en_retard", "WAVE"),
    ("M08", "STUDIO", 30, 1, "+221775550108", "Ndeye", "Thiam", "185000", "10000", 4, None, "ponctuel", "FREE_MONEY"),
]
HISTORY_VACANT = [("M09", "APARTMENT", 75, 2, "FREE"), ("M10", "STUDIO", 33, 1, "MAINTENANCE")]

# (lot, catégorie, priorité, statut, il y a (jours), durée de résolution (jours), description)
HISTORY_TICKETS = [
    ("M01", "AIR_CONDITIONING", "MEDIUM", "CLOSED", 330, 4, "Climatisation du salon qui ne refroidit plus."),
    ("M03", "PLUMBING", "HIGH", "CLOSED", 300, 2, "Fuite au niveau du chauffe-eau de la salle de bain."),
    ("M04", "ELECTRICITY", "MEDIUM", "CLOSED", 270, 6, "Prises de la cuisine sans courant."),
    ("M02", "LOCKSMITH", "LOW", "CLOSED", 240, 3, "Serrure de la porte d'entrée difficile à ouvrir."),
    ("M05", "PAINTING", "LOW", "CLOSED", 210, 12, "Reprise de peinture après une infiltration au plafond."),
    ("M06", "PLUMBING", "MEDIUM", "RESOLVED", 180, 3, "Évier de la cuisine bouché."),
    ("M01", "ELECTRICITY", "HIGH", "CLOSED", 150, 1, "Disjoncteur qui saute à chaque coupure de courant."),
    ("M07", "AIR_CONDITIONING", "MEDIUM", "RESOLVED", 125, 5, "Bruit anormal du climatiseur de la chambre."),
    ("M03", "CLEANING", "LOW", "CLOSED", 100, 2, "Nettoyage des parties communes après travaux."),
    ("M04", "PLUMBING", "URGENT", "RESOLVED", 75, 1, "Dégât des eaux : canalisation percée dans le mur."),
    ("M08", "LOCKSMITH", "MEDIUM", "RESOLVED", 50, 2, "Remplacement du barillet après une perte de clés."),
    ("M06", "ELECTRICITY", "MEDIUM", "RESOLVED", 32, 4, "Éclairage de la cage d'escalier en panne."),
    ("M02", "AIR_CONDITIONING", "HIGH", "IN_PROGRESS", 9, None, "Climatiseur en panne en pleine chaleur, le locataire relance."),
    ("M07", "PLUMBING", "URGENT", "OPEN", 2, None, "Fuite importante sous la douche, l'eau passe chez le voisin du dessous."),
    ("M05", "PAINTING", "LOW", "WAITING", 18, None, "Devis de peinture de la chambre en attente de l'accord du bailleur."),
    ("M10", "ELECTRICITY", "MEDIUM", "OPEN", 5, None, "Remise aux normes du tableau électrique avant relocation."),
]

PROSPECT_NAMES = [
    "Aminata Diop", "Babacar Seck", "Coumba Fall", "Daouda Ba", "Khady Ndiaye", "Lamine Sarr", "Mame Diarra Gueye",
    "Modou Sy", "Nafi Camara", "Pape Diouf", "Rokhaya Mbengue", "Serigne Niang", "Sokhna Wade", "Thierno Barry",
    "Yacine Dieng", "Abdou Karim Sall", "Bineta Touré", "El Hadji Sène", "Fatima Kébé", "Ismaïla Badji",
]
PROSPECT_SOURCES = ["site", "site", "site", "whatsapp", "facebook", "site", "agent"]


def _aware(day, hour=10):
    return timezone.make_aware(datetime.combine(day, time(hour)))


def _unit(building, reference, category, surface, bedrooms, status):
    return Unit.objects.create(
        building=building, reference=reference, category=category, unit_type=dict(Unit.CATEGORY_CHOICES)[category],
        surface=surface, bedrooms=bedrooms, bathrooms=1, status=status,
    )


def _seed_rentals(organization, admin, building, rng, today):
    methods = {method.code: method for method in PaymentMethod.objects.all()}
    for (reference, category, surface, bedrooms, phone, first, last, rent, charges,
         months, end_in, profile, method) in HISTORY_RENTALS:
        unit = _unit(building, reference, category, surface, bedrooms, "FREE")
        tenant_user = register_tenant(organization, phone=phone, first_name=first, last_name=last).user
        lease = LeaseContract.objects.create(
            organization=organization, unit=unit, tenant=tenant_user, created_by=admin,
            start_date=month_start(today, months), end_date=today + timedelta(days=end_in) if end_in else None,
            rent_amount=Decimal(rent), charges_amount=Decimal(charges), deposit_amount=Decimal(rent) * 2,
        )
        change_lease_status(lease, "ACTIVE")
        amount = Decimal(rent) + Decimal(charges)

        for back in range(months, -1, -1):
            due = month_start(today, back).replace(day=5)
            schedule = PaymentSchedule.objects.create(
                organization=organization, lease_contract=lease, schedule_type="RENT", due_date=due, amount_due=amount,
            )
            paid, delay = amount, rng.randint(-4, 0)
            if profile == "tardif":
                delay = rng.randint(6, 22)
            elif profile == "irregulier":
                if back in (4, 1):
                    continue
                if rng.random() < 0.3:
                    paid = (amount / 2).quantize(Decimal("1"))
                delay = rng.randint(0, 15)
            elif profile == "en_retard" and back <= 2:
                continue
            paid_on = due + timedelta(days=delay)
            if paid_on > today:
                continue
            pay_method = methods[method] if rng.random() < 0.85 else methods[rng.choice(sorted(methods))]
            payment = Payment.objects.create(
                organization=organization, payer=tenant_user, recorded_by=admin, amount_paid=paid,
                payment_method=pay_method, reference=f"TRG-{reference}-{due:%Y%m}", note="Loyer et charges",
            )
            Payment.objects.filter(pk=payment.pk).update(payment_date=_aware(paid_on, rng.randint(8, 19)))
            allocate_payment(payment, [{"schedule": schedule, "amount": paid}])


def _seed_tickets(admin, building, rng):
    categories = {category.code: category for category in MaintenanceCategory.objects.all()}
    for reference, category, priority, status, days_ago, duration, description in HISTORY_TICKETS:
        unit = Unit.objects.get(building=building, reference=reference)
        ticket = MaintenanceTicket.objects.create(
            unit=unit, reported_by=admin, priority=priority, status=status, category=categories.get(category),
            description=description,
        )
        created = timezone.now() - timedelta(days=days_ago, hours=rng.randint(0, 8))
        updated = created + timedelta(days=duration, hours=rng.randint(1, 6)) if duration else created + timedelta(hours=3)
        MaintenanceTicket.objects.filter(pk=ticket.pk).update(created_at=created, updated_at=updated)
        MaintenanceLog.objects.create(ticket=ticket, user=admin, message="Demande enregistrée et transmise au prestataire.")


def _seed_interests(organization, rng):
    """Demandes de visite sur les annonces publiées de l'agence, en hausse sur quatre mois."""
    listings = list(Listing.objects.filter(unit__building__property__organization=organization, status="PUBLISHED").order_by("pk"))
    if not listings:
        return
    weights = [3, 2, 2, 1] + [1] * max(0, len(listings) - 4)
    for index in range(34):
        days_ago = int(120 * (1 - (index / 34) ** 0.7)) + rng.randint(0, 3)
        prospect, _ = Prospect.objects.get_or_create(
            organization=organization, phone=f"+22170{index:07d}",
            defaults={"full_name": PROSPECT_NAMES[index % len(PROSPECT_NAMES)], "source": rng.choice(PROSPECT_SOURCES)},
        )
        listing = rng.choices(listings, weights=weights[: len(listings)])[0]
        interest = ProspectInterest.objects.create(
            listing=listing, prospect=prospect,
            message=f"Bonjour, je souhaite visiter « {listing.title} ». Merci de me rappeler.",
        )
        ProspectInterest.objects.filter(pk=interest.pk).update(
            created_at=timezone.now() - timedelta(days=days_ago, hours=rng.randint(0, 10))
        )


def seed_history(organization, admin):
    """Historique réaliste de 12 mois pour la démo du tableau de bord ; ne fait rien s'il existe déjà."""
    name, address, neighborhood, city, lat, lng = HISTORY_PROPERTY
    if Property.objects.filter(organization=organization, name=name).exists():
        return
    rng = random.Random(2026)
    today = date.today()
    prop = Property.objects.create(
        organization=organization, name=name, address=address, neighborhood=neighborhood, city=city,
        latitude=Decimal(lat), longitude=Decimal(lng),
    )
    building = Building.objects.create(property=prop, name="Bloc A")
    for reference, category, surface, bedrooms, status in HISTORY_VACANT:
        _unit(building, reference, category, surface, bedrooms, status)
    _seed_rentals(organization, admin, building, rng, today)
    _seed_tickets(admin, building, rng)
    _seed_interests(organization, rng)


def seed_upcoming(organization):
    """Échéance du mois prochain pour chaque bail actif (idempotent) : alimente « Échéances à venir »."""
    today = date.today()
    next_due = month_start(today, -1).replace(day=5)
    for lease in LeaseContract.objects.filter(organization=organization, status="ACTIVE"):
        PaymentSchedule.objects.get_or_create(
            organization=organization, lease_contract=lease, schedule_type="RENT", due_date=next_due,
            defaults={"amount_due": lease.rent_amount + lease.charges_amount},
        )
