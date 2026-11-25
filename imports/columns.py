"""Colonnes du fichier de reprise : une ligne par lot, avec son bailleur et son bail en cours s'il est loué."""

import unicodedata
from dataclasses import dataclass


def normalize(text):
    """Comparaison tolérante : sans accents, casse, ponctuation ni espaces superflus."""
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    return " ".join("".join(char if char.isalnum() else " " for char in text).split())


@dataclass(frozen=True)
class Column:
    key: str
    header: str
    help: str
    aliases: tuple = ()
    required: bool = False
    width: int = 18
    example: tuple = ("", "", "")
    # Colonnes absentes du modèle d'un propriétaire qui gère ses propres biens.
    agency_only: bool = False


COLUMNS = [
    Column("property", "Bien", "Nom de l'immeuble ou de la villa. Le même nom sur plusieurs lignes désigne le même bien.",
           ("immeuble", "residence", "propriete", "nom du bien"), True, 26,
           ("Résidence Mermoz", "Résidence Mermoz", "Villa Ngor")),
    Column("address", "Adresse", "Facultatif.", (), False, 24, ("Rue 10, Mermoz", "", "Route de Ngor")),
    Column("neighborhood", "Quartier", "Facultatif.", (), False, 16, ("Mermoz", "Mermoz", "Ngor")),
    Column("city", "Ville", "Facultatif : la ville de votre agence par défaut.", (), False, 14, ("Dakar", "Dakar", "Dakar")),
    Column("building", "Bâtiment", "Facultatif.", ("bloc", "batiment bloc"), False, 16, ("Bloc A", "Bloc A", "")),
    Column("unit", "Lot", "Référence du lot, unique dans son bâtiment.", ("reference", "reference du lot", "numero", "numero de lot", "porte"), True, 12,
           ("A101", "A102", "Villa")),
    Column("category", "Catégorie", "Appartement, Studio, Maison, Bureau, Local commercial ou Terrain.", ("type de bien", "nature"), False, 18,
           ("Appartement", "Studio", "Maison")),
    Column("unit_type", "Type", "Facultatif : F3, T2, duplex…", ("type de lot",), False, 10, ("F3", "", "Duplex")),
    Column("surface", "Surface (m²)", "Facultatif.", ("surface", "superficie"), False, 13, ("85", "32", "220")),
    Column("bedrooms", "Chambres", "Facultatif.", ("nombre de chambres",), False, 11, ("2", "1", "4")),
    Column("owner_first", "Prénom bailleur", "Laissez vide si le bien vous appartient.", ("prenom proprietaire",), False, 18,
           ("Seynabou", "", ""), True),
    Column("owner_last", "Nom bailleur", "Nom, ou nom complet si la colonne prénom est vide.", ("bailleur", "proprietaire", "nom proprietaire"), False, 18,
           ("Diagne", "", ""), True),
    Column("owner_phone", "Téléphone bailleur", "Obligatoire si un bailleur est indiqué.", ("telephone proprietaire", "tel bailleur", "tel proprietaire"), False, 20,
           ("77 666 01 01", "", ""), True),
    Column("commission", "Commission (%)", "Votre commission sur les loyers encaissés, pour tout le bien.", ("commission", "taux de commission"), False, 15,
           ("10", "", ""), True),
    Column("tenant_first", "Prénom locataire", "Laissez vide si le lot est libre.", (), False, 18, ("Mamadou", "", "Awa")),
    Column("tenant_last", "Nom locataire", "Nom, ou nom complet si la colonne prénom est vide.", ("locataire", "nom du locataire", "occupant"), False, 18,
           ("Diallo", "", "Ndoye")),
    Column("tenant_phone", "Téléphone locataire", "Obligatoire si un locataire est indiqué.", ("tel locataire", "telephone", "tel", "numero de telephone"), False, 20,
           ("77 555 01 01", "", "78 555 01 04")),
    Column("rent", "Loyer", "Loyer mensuel hors charges, en francs CFA.", ("loyer mensuel", "montant du loyer", "loyer fcfa"), False, 14,
           ("450000", "", "650000")),
    Column("charges", "Charges", "Charges mensuelles.", ("charges mensuelles",), False, 12, ("30000", "", "40000")),
    Column("deposit", "Caution", "Caution déjà versée, pour mémoire.", ("depot de garantie", "garantie"), False, 14, ("900000", "", "1300000")),
    Column("start", "Début du bail", "JJ/MM/AAAA.", ("date d entree", "date de debut", "entree", "debut"), False, 16, ("01/03/2024", "", "15/09/2025")),
    Column("end", "Fin du bail", "Facultatif : JJ/MM/AAAA.", ("date de fin", "fin"), False, 16, ("", "", "14/09/2027")),
    Column("due_day", "Jour d'échéance", "De 1 à 28 ; le 5 par défaut.", ("jour de paiement", "echeance", "jour echeance"), False, 15, ("5", "", "1")),
    Column("frequency", "Fréquence", "Mensuel ou Trimestriel.", ("periodicite", "frequence de paiement"), False, 14, ("Mensuel", "", "Mensuel")),
    Column("arrears", "Impayé à reprendre", "Ce que le locataire doit encore pour les mois passés.", ("impaye", "impayes", "arriere", "arrieres", "reste du", "solde du"), False, 19,
           ("", "", "650000")),
]
BY_KEY = {column.key: column for column in COLUMNS}
HEADERS = {normalize(name): column.key for column in COLUMNS for name in (column.header, *column.aliases)}


def columns_for(organization):
    return [column for column in COLUMNS if not (column.agency_only and organization.kind == "OWNER")]
