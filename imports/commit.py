"""Application d'un plan de reprise, en une seule transaction : tout est créé, ou rien."""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from analytics.dashboard import add_months
from imports.columns import normalize
from imports.plan import build_plan, summarize
from leases.models import LeaseContract, Tenant
from leases.services import activate_lease
from leases.tenants import register_tenant
from organizations.models import Organization
from owners.models import Owner
from owners.owners import register_owner
from payments.models import PaymentSchedule
from payments.schedules import current_period_start, period_months
from properties.models import Building, Property, Unit
from rest_framework.exceptions import ValidationError

CURRENT, NEXT = "CURRENT", "NEXT"
FIRST_PERIODS = [(CURRENT, "Ce mois-ci"), (NEXT, "Le mois prochain")]


def _schedules_from(lease, first_period, today):
    start = current_period_start(lease, today)
    return add_months(start.replace(day=1), period_months(lease)) if first_period == NEXT else start


def _carry_arrears(lease, amount, today):
    """Dette antérieure à Dahoo : une seule échéance, échue, qui ne donne pas droit à une quittance."""
    due_date = max(lease.start_date, today.replace(day=1) - timedelta(days=1))
    PaymentSchedule.objects.create(
        organization_id=lease.organization_id, lease_contract=lease, schedule_type="ARREARS",
        due_date=due_date, amount_due=amount,
    )


@transaction.atomic
def apply_import(organization, raw, *, user, first_period=CURRENT, skip_errors=False, today=None):
    today = today or timezone.localdate()
    # Deux envois simultanés du même fichier : le second attend, puis reconnaît les lots déjà créés.
    organization = Organization.objects.select_for_update().get(pk=organization.pk)
    plan = build_plan(organization, raw, today=today)
    summary = summarize(plan, organization)
    if plan.problems:
        raise ValidationError({"detail": plan.problems[0]})
    if summary["errors"] and not skip_errors:
        raise ValidationError({"detail": f"{summary['errors']} ligne(s) à corriger avant l'import."})
    if not plan.usable:
        raise ValidationError({"detail": "Aucune ligne à importer."})

    properties = {}
    for item in Property.objects.filter(organization=organization).order_by("-id"):
        properties[normalize(item.name)] = item
    buildings = {
        (building.property_id, normalize(building.name)): building
        for building in Building.objects.filter(property__organization=organization).order_by("-id")
    }
    tenants = {tenant.user.phone: tenant.user for tenant in Tenant.objects.filter(organization=organization).select_related("user")}
    owners = {owner.user.phone: owner for owner in Owner.objects.filter(organization=organization).select_related("user")}

    # Le bailleur et la commission d'un bien peuvent n'être écrits que sur une de ses lignes.
    owner_by_property, rate_by_property = {}, {}
    for row in plan.usable:
        if row.owner:
            owner_by_property.setdefault(row.property_key, row.owner)
        if row.commission is not None:
            rate_by_property.setdefault(row.property_key, row.commission)

    def get_owner(person):
        first, last, phone = person
        if phone not in owners:
            owners[phone] = register_owner(organization, phone=phone, first_name=first, last_name=last)
        return owners[phone]

    def get_property(row):
        item = properties.get(row.property_key)
        person = owner_by_property.get(row.property_key)
        if item is None:
            item = Property.objects.create(
                organization=organization, name=row.property_name, address=row.address, neighborhood=row.neighborhood, city=row.city,
                owner=get_owner(person) if person else None,
                commission_rate=rate_by_property.get(row.property_key, 0) if person else 0,
            )
            properties[row.property_key] = item
        elif person and item.owner_id is None:
            item.owner = get_owner(person)
            item.commission_rate = rate_by_property.get(row.property_key, 0)
            item.save(update_fields=["owner", "commission_rate"])
        return item

    def get_unit(row):
        item = get_property(row)
        if row.existing_unit:
            return row.existing_unit
        key = (item.pk, row.building_key)
        if key not in buildings:
            buildings[key] = Building.objects.create(property=item, name=row.building)
        return Unit.objects.create(
            building=buildings[key], reference=row.unit, category=row.category, unit_type=row.unit_type,
            surface=row.surface, bedrooms=row.bedrooms, status="FREE",
        )

    for row in plan.usable:
        unit = get_unit(row)
        if not row.tenant:
            continue
        first, last, phone = row.tenant
        if phone not in tenants:
            tenants[phone] = register_tenant(organization, phone=phone, first_name=first, last_name=last).user
        lease = LeaseContract.objects.create(
            organization=organization, unit=unit, tenant=tenants[phone], created_by=user,
            start_date=row.start, end_date=row.end, rent_amount=row.rent, charges_amount=row.charges,
            deposit_amount=row.deposit, payment_frequency=row.frequency, due_day=row.due_day,
        )
        if row.is_draft:
            continue
        # La caution d'un bail repris a déjà été versée : elle n'est pas redemandée.
        lease, _ = activate_lease(lease, schedules_from=_schedules_from(lease, first_period, today))
        if row.arrears:
            _carry_arrears(lease, row.arrears, today)
    return summary
