"""
Bailleurs de l'agence de démonstration : mandats (commission), dépenses, reversements ; et mise à jour
des encaissements jusqu'à aujourd'hui, pour que la démo reste crédible quelle que soit la date à
laquelle seed_demo est relancé. Déterministe et idempotent.
"""

import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.utils import timezone

from owners.models import Expense, Owner, OwnerPayout
from owners.owners import register_owner
from owners.statements import build_statement
from payments.models import Payment, PaymentAllocation, PaymentMethod, PaymentSchedule
from payments.services import allocate_payment
from properties.models import Property

from ._demo_operations import month_start

# (téléphone, prénom, nom, e-mail, moyen, coordonnées, biens, commission)
OWNERS = [
    ("+221776660101", "Seynabou", "Diagne", "s.diagne@example.com", "BANK_TRANSFER", "IBAN SN08 •••• 4471", ["Résidence Teranga Mermoz"], "10"),
    ("+221776660102", "El Hadji", "Gueye", "", "WAVE", "+221 77 666 01 02", ["Résidence Les Almadies"], "8"),
]
EXPENSES = [
    (0, 12, "REPAIR", "Réparation de la canalisation, M07", "45000"),
    (1, 18, "STAFF", "Gardiennage", "60000"),
    (1, 9, "UTILITIES", "Eau des parties communes", "18500"),
    (2, 22, "REPAIR", "Remplacement du disjoncteur, M01", "32000"),
]

# Locataires qui ne paient pas leurs derniers mois (voir HISTORY_RENTALS et RENTALS).
LATE_PAYERS = {"M07": 3, "B102": 1, "M05": 1}


def _aware(day, hour=10):
    return timezone.make_aware(datetime.combine(day, time(hour)))


def seed_recent_payments(organization, admin):
    """Règle les loyers échus restés impayés depuis la dernière exécution, sauf ceux des retardataires."""
    rng = random.Random(7)
    today = date.today()
    methods = list(PaymentMethod.objects.filter(code__in=("WAVE", "ORANGE_MONEY", "BANK_TRANSFER", "CASH")).order_by("code"))
    schedules = (
        PaymentSchedule.objects.filter(
            organization=organization, is_paid=False, schedule_type="RENT", due_date__lte=today,
            lease_contract__status="ACTIVE", allocations__isnull=True,
        )
        .select_related("lease_contract__unit")
        .order_by("due_date", "id")
    )
    for schedule in schedules:
        lease = schedule.lease_contract
        unpaid_months = LATE_PAYERS.get(lease.unit.reference, 0)
        if unpaid_months and schedule.due_date >= month_start(today, unpaid_months - 1):
            continue
        paid_on = min(today, schedule.due_date + timedelta(days=rng.randint(-3, 9)))
        payment = Payment.objects.create(
            organization=organization, payer_id=lease.tenant_id, recorded_by=admin, amount_paid=schedule.amount_due,
            payment_method=rng.choice(methods), reference=f"TRG-{lease.unit.reference}-{schedule.due_date:%Y%m}",
            note="Loyer et charges", payment_date=min(timezone.now(), _aware(paid_on, rng.randint(8, 18))),
        )
        allocate_payment(payment, [{"schedule": schedule, "amount": schedule.amount_due}])


def seed_owners(organization, admin):
    today = date.today()
    for phone, first, last, email, channel, details, properties, rate in OWNERS:
        owner = Owner.objects.filter(organization=organization, user__phone=phone).first()
        if owner is None:
            owner = register_owner(
                organization, phone=phone, first_name=first, last_name=last, email=email,
                payout_channel=channel, payout_details=details,
            )
        for prop in Property.objects.filter(organization=organization, name__in=properties, owner__isnull=True):
            prop.owner, prop.commission_rate = owner, Decimal(rate)
            prop.save(update_fields=["owner", "commission_rate"])
            # Démo seulement : l'historique existait avant le mandat, on lui applique le même taux.
            PaymentAllocation.objects.filter(
                schedule__lease_contract__unit__building__property=prop, schedule__schedule_type="RENT"
            ).update(commission_rate=Decimal(rate))
        if properties == OWNERS[0][6] and not owner.properties.filter(expenses__isnull=False).exists():
            prop = owner.properties.first()
            for months, day, category, label, amount in EXPENSES:
                spent_on = min(today, month_start(today, months).replace(day=day))
                Expense.objects.create(
                    organization=organization, property=prop, category=category, label=label,
                    amount=Decimal(amount), spent_on=spent_on, recorded_by=admin,
                )
        # Reversement du solde de chaque mois clos, le 8 du mois suivant ; le mois en cours reste à reverser.
        for back in range(14, 0, -1):
            month = month_start(today, back)
            paid_on = month_start(today, back - 1).replace(day=8)
            if paid_on > today or owner.payouts.filter(reference=f"REV-{month:%Y%m}").exists():
                continue
            statement = build_statement(owner, month=month)
            amount = statement["closing_balance"]
            if amount > 0:
                OwnerPayout.objects.create(
                    organization=organization, owner=owner, amount=amount, paid_on=paid_on,
                    channel=channel, reference=f"REV-{month:%Y%m}", recorded_by=admin,
                )
