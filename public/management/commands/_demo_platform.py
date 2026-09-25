"""
Données de démonstration de l'espace plateforme (équipe Dahoo) : dates d'inscription étalées,
abonnements, essais en cours et demandes de démo. Idempotent. N'invente aucune offre : les
abonnements utilisent la première offre active existante (aucun si aucune offre n'est configurée).
Aucune agence n'est laissée expirée, pour que leurs annonces restent visibles sur le portail.
"""

import zlib
from datetime import timedelta

from django.utils import timezone

from organizations.models import Organization
from public.models import DemoRequest
from subscriptions.models import Subscription, SubscriptionPlan

# (agence, inscrite il y a (jours), abonnée depuis (jours) ou None, fin d'essai dans (jours))
PLATFORM_AGENCIES = [
    ("Agence Démo Teranga", 420, 380, None),
    ("Keur Immo", 240, 200, None),
    ("Saly Horizon Immobilier", 150, None, 9),
    ("Rovesta", 60, None, 4),
    ("Mucci Real Estate", 34, None, 20),
    ("Central Estate", 18, None, 26),
]

# (agence, contact, ville, lots, il y a (jours), traitée)
DEMO_REQUESTS = [
    ("Immobilière du Cap-Vert", "Adama Sy", "Dakar", "21-100", 230, True),
    ("Baobab Gestion", "Mariama Diop", "Thiès", "1-20", 205, True),
    ("Keur Immo", "Moussa Fall", "Dakar", "21-100", 245, True),
    ("Saly Horizon Immobilier", "Fatou Ndiaye", "Saly", "21-100", 158, True),
    ("Teranga Syndic", "Ousmane Kane", "Dakar", "101-500", 120, True),
    ("Rovesta", "Ibrahima Sow", "Saint-Louis", "1-20", 66, True),
    ("Mbour Location", "Coumba Sarr", "Mbour", "1-20", 52, True),
    ("Mucci Real Estate", "Khadija Ba", "Dakar", "21-100", 38, True),
    ("Central Estate", "Omar Gueye", "Dakar", "101-500", 22, True),
    ("Petite-Côte Habitat", "Aliou Diagne", "Saly", "21-100", 12, False),
    ("Ziguinchor Immobilier", "Awa Badji", "Ziguinchor", "1-20", 6, False),
    ("Almadies Prestige", "Cheikh Thiam", "Dakar", "500+", 2, False),
]


def seed_platform():
    now = timezone.now()
    today = timezone.localdate()
    plan = SubscriptionPlan.objects.filter(active=True).order_by("pk").first()

    for name, signed_up, subscribed, trial_left in PLATFORM_AGENCIES:
        organization = Organization.objects.filter(name=name).first()
        if organization is None:
            continue
        created = now - timedelta(days=signed_up)
        trial_end = now + timedelta(days=trial_left) if trial_left is not None else created + timedelta(days=30)
        Organization.objects.filter(pk=organization.pk).update(created_at=created, trial_ends_at=trial_end)
        if subscribed is not None and plan is not None:
            Subscription.objects.get_or_create(
                organization=organization, plan=plan, defaults={"start_date": today - timedelta(days=subscribed)}
            )
        elif subscribed is not None:
            # Sans offre configurée, l'agence reste en essai pour ne pas passer en lecture seule.
            Organization.objects.filter(pk=organization.pk).update(trial_ends_at=now + timedelta(days=30))

    for agency, contact, city, units, days_ago, handled in DEMO_REQUESTS:
        phone = f"+2217600{zlib.crc32(agency.encode()) % 100000:05d}"
        demo, created = DemoRequest.objects.get_or_create(
            agency_name=agency, contact_name=contact,
            defaults={"phone": phone, "city": city, "units_range": units, "handled": handled,
                      "message": "Nous souhaitons découvrir Dahoo pour la gestion de nos biens."},
        )
        if created:
            DemoRequest.objects.filter(pk=demo.pk).update(created_at=now - timedelta(days=days_ago, hours=3))
