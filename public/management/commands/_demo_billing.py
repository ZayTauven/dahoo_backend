"""
Démonstration de la vente de Dahoo : offres, règlements d'abonnement, échéances et demande d'offre.
Idempotent : une agence qui a déjà un règlement n'est plus touchée, une offre existante n'est pas modifiée.
"""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from organizations.models import Organization
from payments.models import PaymentMethod
from subscriptions.billing import record_payment
from subscriptions.models import BillingSettings, PlanRequest, SubscriptionPayment, SubscriptionPlan
from users.models import User

# (nom, public, rythme, prix, biens, lots, utilisateurs, phrase)
PLANS = [
    ("Basique", "ALL", "MONTHLY", 15000, 10, 20, 15, "Pour démarrer avec un petit parc"),
    ("Pro", "AGENCY", "MONTHLY", 45000, None, 100, None, "Pour une équipe et plusieurs immeubles"),
    ("Propriétaire", "OWNER", "YEARLY", 60000, None, 5, 2, "Quelques biens, sans bailleur"),
]
# (agence, offre, mois, réglé il y a (jours), remise, moyen, référence, essai terminé il y a (jours) ou None)
PAYMENTS = [
    ("Agence Démo Teranga", "Basique", 1, 45, 0, "WAVE", "WV-20418", None),
    ("Agence Démo Teranga", "Basique", 3, 14, 0, "BANK_TRANSFER", "VIR-0931", None),
    # Se termine dans quelques jours : à renouveler.
    ("Keur Immo", "Basique", 1, 26, 0, "ORANGE_MONEY", "OM-77120", None),
    # Réglé pendant l'essai : les jours d'essai restants sont offerts.
    ("Rovesta", "Basique", 3, 1, 5000, "WAVE", "WV-20533", None),
    # Échu depuis deux semaines : en lecture seule.
    ("Central Estate", "Basique", 1, 45, 0, "CASH", "", 50),
]
REQUEST = ("Saly Horizon Immobilier", "Pro", "Nous avons 40 lots à Saly et Mbour, nous voulons démarrer avant la fin de l'essai.")


def seed_billing():
    today = timezone.localdate()
    for name, audience, billing, price, properties, units, users, description in PLANS:
        plan, created = SubscriptionPlan.objects.get_or_create(name=name, defaults={
            "audience": audience, "billing_type": billing, "price": price, "description": description,
            "max_properties": properties, "max_units": units, "max_users": users,
        })
        if not created and not plan.description:
            SubscriptionPlan.objects.filter(pk=plan.pk).update(description=description)

    settings = BillingSettings.load()
    if not settings.payment_instructions:
        settings.payment_instructions = "Wave, Orange Money ou virement, en indiquant le nom de l'agence."
        settings.save()

    staff = User.objects.filter(is_staff=True).order_by("pk").first()
    if staff is None:
        return
    paid = set(SubscriptionPayment.objects.values_list("subscription__organization__name", flat=True))
    for name, plan, months, days_ago, discount, method, reference, trial_ended in PAYMENTS:
        organization = Organization.objects.filter(name=name).first()
        if organization is None:
            continue
        # À chaque passage : seed_platform vient de remettre l'essai en cours.
        if trial_ended is not None:
            organization.trial_ends_at = timezone.now() - timedelta(days=trial_ended)
            organization.save(update_fields=["trial_ends_at"])
        if name in paid:
            continue
        record_payment(
            organization, user=staff, plan=SubscriptionPlan.objects.get(name=plan), quantity=months, discount=Decimal(discount),
            paid_on=today - timedelta(days=days_ago), method=PaymentMethod.objects.get(code=method), reference=reference,
        )

    name, plan, message = REQUEST
    organization = Organization.objects.filter(name=name).first()
    if organization and not PlanRequest.objects.filter(organization=organization).exists():
        admin = organization.memberships.filter(is_active=True).select_related("user").first()
        if admin:
            # Sans passer par request_plan : la démonstration n'envoie aucun e-mail à l'équipe.
            PlanRequest.objects.create(organization=organization, requested_by=admin.user, plan=SubscriptionPlan.objects.get(name=plan), message=message)
