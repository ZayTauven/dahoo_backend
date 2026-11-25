"""
Contrôle d'un fichier de reprise : chaque ligne devient un plan (ce qui sera créé) avec ses remarques.
Rien n'est écrit ici ; `imports.commit` applique le plan.

Renvoyer deux fois le même fichier ne crée rien en double : un lot déjà présent est reconnu, et un bail
déjà actif avec le même locataire est ignoré.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from django.utils import timezone

from imports import values
from imports.columns import BY_KEY, normalize
from leases.models import LeaseContract, Tenant
from owners.models import Owner
from properties.models import Property, Unit
from subscriptions.services import remaining_quota

READY, WARNING, SKIPPED, ERROR = "READY", "WARNING", "SKIPPED", "ERROR"
ROW_STATUSES = [(READY, "Prêt"), (WARNING, "À vérifier"), (SKIPPED, "Déjà présent"), (ERROR, "À corriger")]

DEFAULT_BUILDING = "Bâtiment principal"
CATEGORIES = {
    "APARTMENT": ("appartement", "appart", "apt", "appt", "duplex"),
    "STUDIO": ("studio", "chambre"),
    "HOUSE": ("maison", "villa", "maison villa"),
    "OFFICE": ("bureau", "bureaux", "plateau"),
    "SHOP": ("local commercial", "local", "boutique", "magasin", "commerce", "cantine"),
    "LAND": ("terrain",),
}
CATEGORY_BY_NAME = {name: code for code, names in CATEGORIES.items() for name in names}
FREQUENCIES = {"mensuel": "MONTHLY", "mois": "MONTHLY", "trimestriel": "QUARTERLY", "trimestre": "QUARTERLY"}
# « property » est un mot de Python : l'attribut de la ligne porte un autre nom.
ATTRIBUTES = {"property": "property_name"}
LENGTHS = {
    "property": 255, "neighborhood": 100, "city": 100, "building": 255, "unit": 50, "unit_type": 50,
    "owner_first": 100, "owner_last": 100, "tenant_first": 100, "tenant_last": 100,
}


@dataclass
class Message:
    column: str
    text: str
    error: bool = False


@dataclass
class RowPlan:
    line: int
    messages: list = field(default_factory=list)
    skipped: bool = False

    property_name: str = ""
    address: str = ""
    neighborhood: str = ""
    city: str = ""
    building: str = ""
    unit: str = ""
    category: str = "APARTMENT"
    unit_type: str = ""
    surface: float = 0
    bedrooms: int | None = None

    owner: tuple | None = None  # (prénom, nom, téléphone)
    commission: Decimal | None = None
    tenant: tuple | None = None  # (prénom, nom, téléphone)

    rent: Decimal = Decimal("0")
    charges: Decimal = Decimal("0")
    deposit: Decimal = Decimal("0")
    start: date | None = None
    end: date | None = None
    due_day: int = 5
    frequency: str = "MONTHLY"
    arrears: Decimal = Decimal("0")

    # Objets de l'agence reconnus.
    existing_unit: Unit | None = None

    def error(self, column, text):
        self.messages.append(Message(column, text, True))

    def warn(self, column, text):
        self.messages.append(Message(column, text))

    @property
    def has_errors(self):
        return any(message.error for message in self.messages)

    @property
    def status(self):
        if self.has_errors:
            return ERROR
        if self.skipped:
            return SKIPPED
        return WARNING if self.messages else READY

    @property
    def usable(self):
        return not self.has_errors and not self.skipped

    @property
    def property_key(self):
        return normalize(self.property_name)

    @property
    def building_key(self):
        return normalize(self.building)

    @property
    def unit_key(self):
        return self.property_key, self.building_key, normalize(self.unit)

    @property
    def is_draft(self):
        """Bail à venir : créé en brouillon, il s'active à l'entrée du locataire."""
        return bool(self.tenant and self.start and self.start > timezone.localdate())


@dataclass
class Plan:
    rows: list
    ignored_columns: list
    problems: list = field(default_factory=list)

    @property
    def usable(self):
        return [row for row in self.rows if row.usable]


def _read(row, cells, key, parse, default=None):
    """Valeur d'une cellule ; une valeur illisible devient une erreur de ligne, pas une exception."""
    cell = cells.get(key)
    if cell is None:
        return default
    try:
        return parse(cell)
    except (ValueError, ArithmeticError) as error:
        row.error(key, str(error) if isinstance(error, ValueError) else f"« {values.text(cell)} » n'est pas lisible.")
        return default


def _read_unit(row, cells, organization):
    for key in ("property", "address", "neighborhood", "city", "building", "unit", "unit_type"):
        setattr(row, ATTRIBUTES.get(key, key), values.text(cells.get(key)))
    for key in ("property", "unit"):
        if not getattr(row, ATTRIBUTES.get(key, key)):
            row.error(key, f"« {BY_KEY[key].header} » est obligatoire.")
    row.building = row.building or DEFAULT_BUILDING
    row.city = row.city or organization.city or "Dakar"
    row.address = row.address or ", ".join(part for part in (row.neighborhood, row.city) if part)
    row.surface = _read(row, cells, "surface", values.number, 0)
    row.bedrooms = _read(row, cells, "bedrooms", values.integer)
    if row.bedrooms is not None and row.bedrooms > 100:
        row.error("bedrooms", "Nombre de chambres trop élevé.")
    category = values.text(cells.get("category"))
    if category:
        code = CATEGORY_BY_NAME.get(normalize(category))
        if code:
            row.category = code
        else:
            row.unit_type = row.unit_type or category[:50]
            row.warn("category", f"Catégorie « {category} » inconnue : « Appartement » retenu.")
    if not row.unit_type:
        row.unit_type = dict(Unit.CATEGORY_CHOICES)[row.category]


def _read_person(row, cells, prefix, label):
    first, last = values.text(cells.get(f"{prefix}_first")), values.text(cells.get(f"{prefix}_last"))
    number = _read(row, cells, f"{prefix}_phone", values.phone)
    has_phone = cells.get(f"{prefix}_phone") is not None
    if not first and not last:
        if has_phone:
            row.error(f"{prefix}_last", f"Téléphone sans nom de {label}.")
        return None
    if not has_phone:
        row.error(f"{prefix}_phone", f"Le téléphone du {label} est obligatoire.")
    return (*values.full_name(first, last), number) if number else None


def _read_lease(row, cells, today):
    amounts = ("rent", "charges", "deposit", "arrears")
    for key in amounts:
        setattr(row, key, _read(row, cells, key, values.money, Decimal("0")))
    row.start = _read(row, cells, "start", values.day)
    row.end = _read(row, cells, "end", values.day)
    named = any(cells.get(key) for key in ("tenant_first", "tenant_last", "tenant_phone"))
    if not named:
        if row.arrears:
            row.error("arrears", "Impayé sans locataire.")
        elif row.rent:
            row.warn("rent", "Lot libre : le loyer indiqué n'est pas repris.")
        return
    if not row.rent:
        row.error("rent", "Le loyer est obligatoire pour un lot loué.")
    if cells.get("start") is None:
        row.start = today.replace(day=1)
        row.warn("start", f"Début du bail absent : {row.start:%d/%m/%Y} retenu.")
    if row.start and not 1950 <= row.start.year <= 2100:
        row.error("start", "Année du début du bail improbable.")
    if row.end and row.start and row.end <= row.start:
        row.error("end", "La fin du bail doit suivre son début.")
    elif row.end and row.end < today:
        row.error("end", "Ce bail est déjà terminé : laissez la fin vide s'il continue, ou retirez le locataire.")
    frequency = values.text(cells.get("frequency"))
    if frequency:
        row.frequency = FREQUENCIES.get(normalize(frequency), "")
        if not row.frequency:
            row.error("frequency", "Mensuel ou Trimestriel.")
    day = _read(row, cells, "due_day", values.integer, 5)
    if day < 1 or day > 31:
        row.error("due_day", "Le jour d'échéance va de 1 à 28.")
    elif day > 28:
        row.warn("due_day", f"Le {day} n'existe pas tous les mois : le 28 est retenu.")
        day = 28
    row.due_day = day
    if row.start and row.start > today:
        if row.arrears:
            row.error("arrears", "Impayé sur un bail qui n'a pas commencé.")
        row.warn("start", "Bail à venir : créé en brouillon, à activer à l'entrée du locataire.")


def _person_label(person):
    return f"{person[0]} {person[1]}".strip()


def build_plan(organization, raw, *, today=None):
    today = today or timezone.localdate()
    is_agency = organization.kind == "AGENCY"

    properties = {}
    for item in Property.objects.filter(organization=organization).select_related("owner__user").order_by("-id"):
        properties[normalize(item.name)] = item
    units = {
        (normalize(unit.building.property.name), normalize(unit.building.name), normalize(unit.reference)): unit
        for unit in Unit.objects.filter(building__property__organization=organization).select_related("building__property")
    }
    active_leases = {
        lease.unit_id: lease
        for lease in LeaseContract.objects.filter(organization=organization, status="ACTIVE").select_related("tenant")
    }
    open_drafts = {
        (lease.unit_id, lease.tenant.phone)
        for lease in LeaseContract.objects.filter(organization=organization, status="DRAFT").select_related("tenant")
    }
    people = {
        "tenant": {t.user.phone: f"{t.first_name} {t.last_name}".strip() for t in Tenant.objects.filter(organization=organization).select_related("user")},
        "owner": {o.user.phone: o.full_name for o in Owner.objects.filter(organization=organization).select_related("user")},
    }
    # Ce que les lignes précédentes ont déjà fixé : {clé: (valeur, ligne)}.
    seen_units, seen_owner, seen_rate, seen_people = {}, {}, {}, {}

    rows = []
    for raw_row in raw.rows:
        row, cells = RowPlan(raw_row.line), raw_row.cells
        rows.append(row)
        for key, limit in LENGTHS.items():
            if len(values.text(cells.get(key))) > limit:
                row.error(key, f"Texte trop long ({limit} caractères au plus).")
        _read_unit(row, cells, organization)
        row.tenant = _read_person(row, cells, "tenant", "locataire")
        if is_agency:
            row.owner = _read_person(row, cells, "owner", "bailleur")
            row.commission = _read(row, cells, "commission", values.percent)
        _read_lease(row, cells, today)
        if row.has_errors:
            continue

        # --- Lot
        if row.unit_key in seen_units:
            row.error("unit", f"Lot déjà présent à la ligne {seen_units[row.unit_key]}.")
            continue
        seen_units[row.unit_key] = row.line
        row.existing_unit = units.get(row.unit_key)
        if row.existing_unit:
            lease = active_leases.get(row.existing_unit.pk)
            if not row.tenant:
                row.skipped = True
                row.warn("unit", "Ce lot existe déjà.")
            elif lease and lease.tenant.phone == row.tenant[2]:
                row.skipped = True
                row.warn("unit", "Ce lot et son bail existent déjà.")
            elif lease:
                row.error("tenant_phone", "Ce lot a déjà un bail actif avec un autre locataire.")
            elif (row.existing_unit.pk, row.tenant[2]) in open_drafts:
                row.skipped = True
                row.warn("unit", "Un brouillon de bail existe déjà pour ce lot et ce locataire.")
            elif row.existing_unit.status in ("SOLD", "MAINTENANCE") and not row.is_draft:
                row.error("unit", f"Ce lot est « {row.existing_unit.get_status_display()} » dans Dahoo : remettez-le en « Libre ».")
            else:
                row.warn("unit", "Lot déjà présent : seul son bail sera créé.")

        # --- Personnes : un numéro désigne une seule personne
        for kind in ("tenant", "owner"):
            person = getattr(row, kind)
            if not person:
                continue
            known = people[kind].get(person[2])
            if known and normalize(known) != normalize(_person_label(person)):
                row.warn(f"{kind}_phone", f"Numéro déjà enregistré au nom de {known} : cette fiche est reprise.")
            elif not known:
                name, line = seen_people.setdefault((kind, person[2]), (_person_label(person), row.line))
                if normalize(name) != normalize(_person_label(person)):
                    row.error(f"{kind}_phone", f"Ce numéro est celui de {name} à la ligne {line}.")

        # --- Bailleur et commission : un seul par bien
        existing = properties.get(row.property_key)
        if existing and existing.owner and row.owner and existing.owner.user.phone != row.owner[2]:
            row.error("owner_phone", f"Ce bien appartient déjà à {existing.owner.full_name} dans Dahoo.")
        if row.owner:
            phone, line = seen_owner.setdefault(row.property_key, (row.owner[2], row.line))
            if phone != row.owner[2]:
                row.error("owner_phone", f"Un autre bailleur est indiqué pour ce bien à la ligne {line}.")
        if row.commission is not None:
            rate, line = seen_rate.setdefault(row.property_key, (row.commission, row.line))
            if rate != row.commission:
                row.warn("commission", f"Commission différente de la ligne {line} : {rate.normalize():f} % retenus pour ce bien.")
            elif existing and existing.owner and existing.commission_rate != row.commission and not row.skipped:
                row.warn("commission", "Commission déjà réglée dans Dahoo : elle n'est pas modifiée.")

    plan = Plan(rows, raw.ignored_columns)
    _check_quotas(organization, plan, properties)
    return plan


def _check_quotas(organization, plan, properties):
    usable = plan.usable
    needs = {
        "property": ("biens", len({row.property_key for row in usable} - set(properties))),
        "unit": ("lots", sum(row.existing_unit is None for row in usable)),
    }
    for resource, (label, needed) in needs.items():
        left = remaining_quota(organization, resource)
        if left is not None and needed > left:
            plan.problems.append(f"Votre abonnement permet encore {left} {label}, le fichier en ajoute {needed}. Passez à une offre supérieure ou réduisez le fichier.")


def summarize(plan, organization):
    """Ce que l'import créera, pour l'écran de contrôle."""
    usable = plan.usable
    names = {normalize(name) for name in Property.objects.filter(organization=organization).values_list("name", flat=True)}
    tenants = set(Tenant.objects.filter(organization=organization).values_list("user__phone", flat=True))
    owners = set(Owner.objects.filter(organization=organization).values_list("user__phone", flat=True))
    leased = [row for row in usable if row.tenant]
    return {
        "rows": len(plan.rows),
        "ready": len(usable),
        "warnings": sum(row.status == WARNING for row in plan.rows),
        "skipped": sum(row.status == SKIPPED for row in plan.rows),
        "errors": sum(row.status == ERROR for row in plan.rows),
        "properties": len({row.property_key for row in usable} - names),
        "units": sum(row.existing_unit is None for row in usable),
        "owners": len({row.owner[2] for row in usable if row.owner} - owners),
        "tenants": len({row.tenant[2] for row in leased} - tenants),
        "leases": len(leased),
        "monthly_rent": sum((row.rent + row.charges for row in leased if not row.is_draft), Decimal("0")),
        "arrears": sum((row.arrears for row in leased), Decimal("0")),
    }
