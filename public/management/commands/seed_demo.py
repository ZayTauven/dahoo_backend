"""
Données de démonstration : agences, biens, annonces publiées avec photos, et pour la première agence
une activité de gestion (locataires, baux, échéances, paiements, maintenance).
Idempotent (relançable sans doublon). Réservé au développement et aux démonstrations clients.
"""

from decimal import Decimal
from itertools import cycle
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from access.models import Role
from listings.models import Listing, ListingPhoto
from organizations.models import Membership, Organization
from organizations.services import add_member
from properties.models import Building, Property, Unit
from users.models import User

from ._demo_operations import seed_operations, seed_reference_data

DEMO_PASSWORD = "DahooDemo!2026"
PHOTO_PATTERNS = ("property-*.webp", "slider-*.webp", "immobilier-01.webp", "immobilier-02.webp")

# (agence, ville, téléphone, administrateur, biens)
# bien : (nom, adresse, quartier, ville, lat, lng, [lots])
# lot : (référence, catégorie, surface, chambres, sdb, parking, meublé, annonce)
# annonce : (type, prix, titre, description)
AGENCIES = [
    {
        "name": "Agence Démo Teranga",
        "city": "Dakar",
        "phone": "+221338000000",
        "email": "contact@teranga-demo.sn",
        "admin": ("+221770000001", "Awa", "Diop"),
        "properties": [
            ("Résidence Les Almadies", "Route des Almadies", "Almadies", "Dakar", "14.745200", "-17.513100", [
                ("A101", "APARTMENT", 60, 2, 1, 1, False, ("RENT", "450000", "Appartement T2 lumineux aux Almadies",
                    "Appartement de deux pièces au premier étage, séjour ouvert sur balcon, cuisine équipée. "
                    "Résidence sécurisée avec gardien 24 h/24, à cinq minutes des plages.")),
                ("A202", "APARTMENT", 85, 3, 2, 1, True, ("RENT", "750000", "T3 meublé avec vue mer aux Almadies",
                    "Grand trois pièces entièrement meublé, deux chambres climatisées, deux salles d'eau. "
                    "Vue dégagée sur l'océan, parking privatif et groupe électrogène.")),
                ("A303", "APARTMENT", 110, 3, 2, 2, False, ("SALE", "145000000", "Appartement familial à vendre, Almadies",
                    "Trois chambres dont une suite parentale, double séjour, terrasse de 20 m². "
                    "Titre foncier, résidence récente avec ascenseur.")),
            ]),
            ("Villa Ngor Virage", "Route de Ngor", "Ngor", "Dakar", "14.749300", "-17.516800", [
                ("V1", "HOUSE", 320, 5, 4, 3, False, ("SALE", "285000000", "Villa contemporaine avec piscine à Ngor",
                    "Villa de cinq chambres sur un terrain de 500 m², piscine, jardin arboré et dépendance. "
                    "Quartier calme, proche de l'île de Ngor et des écoles internationales.")),
            ]),
        ],
    },
    {
        "name": "Keur Immo",
        "city": "Dakar",
        "phone": "+221338210000",
        "email": "bonjour@keurimmo.sn",
        "admin": ("+221770000002", "Moussa", "Fall"),
        "properties": [
            ("Immeuble Mermoz", "Avenue Cheikh Anta Diop", "Mermoz", "Dakar", "14.708100", "-17.471900", [
                ("M11", "APARTMENT", 55, 2, 1, 0, False, ("RENT", "350000", "Deux pièces rénové à Mermoz",
                    "Appartement rénové en 2025, deux pièces, cuisine américaine. "
                    "Proche de l'université et des commerces, idéal pour un jeune couple.")),
                ("M24", "STUDIO", 32, 1, 1, 0, True, ("RENT", "220000", "Studio meublé à Mermoz",
                    "Studio meublé et équipé, climatisation, internet fibre inclus dans les charges. "
                    "Disponible immédiatement.")),
            ]),
            ("Centre d'affaires du Plateau", "Rue Carnot", "Plateau", "Dakar", "14.668400", "-17.434000", [
                ("B3", "OFFICE", 140, None, 2, 2, False, ("RENT", "1200000", "Plateau de bureaux au cœur du Plateau",
                    "Plateau de 140 m² cloisonnable, climatisation centrale, fibre, deux places de parking. "
                    "Immeuble de standing avec accueil et sécurité.")),
                ("RDC", "SHOP", 90, None, 1, 0, False, ("RENT", "900000", "Local commercial sur rue au Plateau",
                    "Local en rez-de-chaussée avec vitrine sur rue passante, réserve et sanitaires. "
                    "Convient à une boutique, une agence ou un showroom.")),
            ]),
            ("Résidence Point E", "Rue de Kaolack", "Point E", "Dakar", "14.697600", "-17.460100", [
                ("PE2", "APARTMENT", 95, 3, 2, 1, False, ("SALE", "98000000", "Appartement 3 chambres à vendre au Point E",
                    "Appartement traversant, trois chambres, deux salles de bain, balcon filant. "
                    "Quartier résidentiel recherché, proche des ambassades.")),
            ]),
        ],
    },
    {
        "name": "Saly Horizon Immobilier",
        "city": "Saly",
        "phone": "+221339570000",
        "email": "contact@saly-horizon.sn",
        "admin": ("+221770000003", "Fatou", "Ndiaye"),
        "properties": [
            ("Villa Saly Portudal", "Route de Saly Portudal", "Saly Portudal", "Saly", "14.444100", "-17.009700", [
                ("SP1", "HOUSE", 240, 4, 3, 2, True, ("SALE", "120000000", "Villa avec piscine à Saly Portudal",
                    "Villa de quatre chambres entièrement meublée, piscine, jardin tropical, à 300 m de la plage. "
                    "Idéale en résidence secondaire ou en location saisonnière.")),
            ]),
            ("Résidence Saly Centre", "Avenue principale", "Saly Centre", "Saly", "14.447300", "-17.013900", [
                ("C5", "STUDIO", 38, 1, 1, 0, True, ("RENT", "180000", "Studio meublé à Saly Centre",
                    "Studio meublé avec kitchenette et terrasse, piscine commune dans la résidence. "
                    "À deux pas des restaurants et de la plage.")),
            ]),
            ("Villas de Ngaparou", "Front de mer", "Ngaparou", "Saly", "14.462000", "-17.059900", [
                ("N2", "HOUSE", 280, 5, 5, 3, True, ("RENT", "1500000", "Villa pieds dans l'eau à Ngaparou",
                    "Villa de standing directement sur la plage, cinq suites, grande terrasse et piscine à débordement. "
                    "Location à l'année, personnel de maison possible.")),
            ]),
            ("Terrains de la Somone", "Route de la lagune", "Somone", "Saly", "14.488600", "-17.080600", [
                ("T7", "LAND", 600, None, None, None, False, ("SALE", "35000000", "Terrain viabilisé de 600 m² à la Somone",
                    "Parcelle viabilisée (eau, électricité) avec titre foncier, dans un lotissement proche de la lagune. "
                    "Constructible immédiatement.")),
            ]),
        ],
    },
]


class Command(BaseCommand):
    help = "Crée les données de démonstration du portail (agences, biens, annonces publiées avec photos)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--photos",
            default="../dahoo_front/public/images/site",
            help="Dossier des photos à attribuer aux annonces (défaut : visuels du front).",
        )
        parser.add_argument(
            "--refresh-photos",
            action="store_true",
            help="Remplace les photos des annonces de démonstration (après un changement du jeu de photos).",
        )

    @transaction.atomic
    def handle(self, photos, refresh_photos=False, **options):
        photo_dir = Path(photos)
        # Uniquement de vraies photos de biens (les autres visuels du site sont des illustrations,
        # des monuments étrangers ou des portraits, sans rapport avec une annonce).
        pool = sorted(
            p for pattern in PHOTO_PATTERNS for p in photo_dir.glob(pattern)
        )
        if not pool:
            raise CommandError(f"Aucune photo trouvée dans {photo_dir.resolve()}.")
        photo_cycle = cycle(pool)
        admin_role = Role.objects.get(code="ORG_ADMIN")
        created = 0

        for spec in AGENCIES:
            organization, _ = Organization.objects.get_or_create(
                name=spec["name"], defaults={"city": spec["city"], "phone": spec["phone"], "email": spec["email"]}
            )
            Organization.objects.filter(pk=organization.pk).update(phone=spec["phone"], email=spec["email"], city=spec["city"])

            phone, first_name, last_name = spec["admin"]
            user = User.objects.filter(phone=phone).first()
            if user is None:
                add_member(organization, admin_role, phone=phone, first_name=first_name, last_name=last_name, password=DEMO_PASSWORD)
                user = User.objects.get(phone=phone)
            elif not Membership.objects.filter(user=user, organization=organization).exists():
                add_member(organization, admin_role, phone=phone, existing_user=user)

            for name, address, neighborhood, city, lat, lng, units in spec["properties"]:
                prop, _ = Property.objects.update_or_create(
                    organization=organization,
                    name=name,
                    defaults={"address": address, "neighborhood": neighborhood, "city": city,
                              "latitude": Decimal(lat), "longitude": Decimal(lng)},
                )
                building, _ = Building.objects.get_or_create(property=prop, name="Bâtiment principal")
                for reference, category, surface, bedrooms, bathrooms, parking, furnished, listing in units:
                    unit, _ = Unit.objects.update_or_create(
                        building=building,
                        reference=reference,
                        defaults={"category": category, "unit_type": dict(Unit.CATEGORY_CHOICES)[category],
                                  "surface": surface, "bedrooms": bedrooms, "bathrooms": bathrooms,
                                  "parking_spaces": parking, "is_furnished": furnished, "status": "FREE"},
                    )
                    listing_type, price, title, description = listing
                    ad, was_created = Listing.objects.get_or_create(
                        unit=unit,
                        title=title,
                        defaults={"created_by": user, "description": description, "listing_type": listing_type,
                                  "price": Decimal(price), "status": "PUBLISHED", "published_at": timezone.now()},
                    )
                    created += was_created
                    if refresh_photos:
                        for photo in ad.photos.all():
                            photo.delete()
                    if not ad.photos.exists():
                        for position in range(3):
                            source = next(photo_cycle)
                            with source.open("rb") as handle:
                                ListingPhoto.objects.create(
                                    listing=ad, position=position, alt=f"{title} — photo {position + 1}",
                                    image=File(handle, name=source.name),
                                )

        # Partie gestion (baux, loyers, maintenance) pour la première agence de démonstration.
        seed_reference_data()
        teranga = Organization.objects.get(name=AGENCIES[0]["name"])
        seed_operations(teranga, User.objects.get(phone=AGENCIES[0]["admin"][0]))

        total = Listing.objects.filter(status="PUBLISHED").count()
        self.stdout.write(self.style.SUCCESS(
            f"Démonstration prête : {created} annonce(s) créée(s), {total} annonce(s) publiée(s). "
            f"Comptes administrateurs : +221770000001 / 2 / 3, mot de passe {DEMO_PASSWORD}"
        ))
