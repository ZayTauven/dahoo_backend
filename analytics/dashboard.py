"""
Tableau de bord de l'espace agence : indicateurs calculés à la volée à partir des données de gestion
(lots, baux, échéances, paiements, maintenance, annonces et demandes de visite).

Les volumes d'une agence restent modestes (quelques centaines de lots) : un calcul direct, en une
poignée de requêtes agrégées, est plus sûr qu'un cache à invalider. Chaque section n'est calculée
que si le rôle du membre a la capability correspondante ; sinon elle vaut `None`.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, F, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone

from leases.models import LeaseContract
from listings.models import Listing, ProspectInterest
from listings.photos import cover_url
from maintenance.models import MaintenanceTicket
from payments.models import Payment, PaymentAllocation, PaymentSchedule
from properties.models import Building, Property, Unit

ZERO = Decimal("0")
OPEN_TICKET_STATUSES = ("OPEN", "IN_PROGRESS", "WAITING")
DONE_TICKET_STATUSES = ("RESOLVED", "CLOSED")
URGENT_PRIORITIES = ("HIGH", "URGENT")
PRIORITY_ORDER = {"URGENT": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
AGING_BUCKETS = [("0-30", 0, 30), ("31-60", 31, 60), ("61-90", 61, 90), ("90+", 91, None)]


def add_months(day, months):
    month = day.month - 1 + months
    return date(day.year + month // 12, month % 12 + 1, 1)


def month_keys(today, months):
    """Premiers jours des `months` derniers mois, du plus ancien au mois courant."""
    current = today.replace(day=1)
    return [add_months(current, -back) for back in range(months - 1, -1, -1)]


def _key(value):
    """Clé « AAAA-MM » d'une date ou d'un datetime (TruncMonth renvoie selon le champ)."""
    return value.strftime("%Y-%m")


def _amount(value):
    return value if value is not None else ZERO


def _tenant_name(user):
    if user is None:
        return ""
    name = f"{user.first_name} {user.last_name}".strip()
    return name or user.phone


def _schedule_row(schedule, today):
    lease = schedule.lease_contract
    return {
        "id": schedule.pk,
        "due_date": schedule.due_date,
        "amount_due": schedule.amount_due,
        "remaining": schedule.remaining,
        "days_late": max(0, (today - schedule.due_date).days),
        "tenant": _tenant_name(lease.tenant) if lease else "",
        "unit": lease.unit.reference if lease else "",
        "lease_id": lease.pk if lease else None,
    }


def schedules_with_remaining(organization):
    allocated = (
        PaymentAllocation.objects.filter(schedule=OuterRef("pk"))
        .values("schedule")
        .annotate(total=Sum("allocated_amount"))
        .values("total")
    )
    return (
        PaymentSchedule.objects.filter(organization=organization)
        .annotate(
            allocated=Coalesce(Subquery(allocated, output_field=DecimalField(max_digits=14, decimal_places=2)), Value(ZERO)),
        )
        .annotate(remaining=F("amount_due") - F("allocated"))
    )


def portfolio_section(organization):
    units = Unit.objects.filter(building__property__organization=organization)
    by_status = dict(units.values_list("status").annotate(count=Count("id")))
    by_category = list(units.values("category").annotate(count=Count("id")).order_by("-count"))
    labels = dict(Unit.CATEGORY_CHOICES)
    total = sum(by_status.values())
    rented = by_status.get("RENTED", 0)
    rentable = total - by_status.get("SOLD", 0)
    return {
        "properties": Property.objects.filter(organization=organization).count(),
        "buildings": Building.objects.filter(property__organization=organization).count(),
        "units": total,
        "units_by_status": {status: by_status.get(status, 0) for status, _ in Unit.STATUS_CHOICES},
        "units_by_category": [
            {"category": row["category"], "label": labels.get(row["category"], row["category"]), "count": row["count"]}
            for row in by_category
        ],
        "occupancy_rate": round(rented / rentable * 100, 1) if rentable else None,
    }


def leases_section(organization, today):
    leases = LeaseContract.objects.filter(organization=organization)
    active = leases.filter(status="ACTIVE")
    horizon = today + timedelta(days=90)
    ending = (
        active.filter(end_date__isnull=False, end_date__gte=today, end_date__lte=horizon)
        .select_related("tenant", "unit")
        .order_by("end_date")[:5]
    )
    return {
        "active": active.count(),
        "drafts": leases.filter(status="DRAFT").count(),
        "tenants": active.values("tenant").distinct().count(),
        "monthly_rent_roll": _amount(active.aggregate(total=Sum(F("rent_amount") + F("charges_amount")))["total"]),
        "ending_soon": [
            {
                "id": lease.pk,
                "tenant": _tenant_name(lease.tenant),
                "unit": lease.unit.reference,
                "end_date": lease.end_date,
                "days_left": (lease.end_date - today).days,
            }
            for lease in ending
        ],
    }


def finance_section(organization, today, months):
    keys = month_keys(today, months)
    start = keys[0]
    schedules = schedules_with_remaining(organization)
    payments = Payment.objects.filter(organization=organization)

    expected = {
        _key(row["month"]): row["total"]
        for row in schedules.filter(due_date__gte=start, due_date__lt=add_months(today.replace(day=1), 1))
        .annotate(month=TruncMonth("due_date"))
        .values("month")
        .annotate(total=Sum("amount_due"))
    }
    collected = {
        _key(timezone.localtime(row["month"]) if timezone.is_aware(row["month"]) else row["month"]): row["total"]
        for row in payments.filter(payment_date__date__gte=start)
        .annotate(month=TruncMonth("payment_date"))
        .values("month")
        .annotate(total=Sum("amount_paid"))
    }
    monthly = []
    for month in keys:
        key = _key(month)
        exp, col = _amount(expected.get(key)), _amount(collected.get(key))
        monthly.append({
            "month": key,
            "expected": exp,
            "collected": col,
            "rate": round(float(col / exp * 100), 1) if exp else None,
        })

    # Mois courant : taux de recouvrement des échéances du mois (ce qui a été affecté à ces échéances).
    month_start = today.replace(day=1)
    in_month = {"due_date__gte": month_start, "due_date__lt": add_months(month_start, 1)}
    month_expected = _amount(
        PaymentSchedule.objects.filter(organization=organization, **in_month).aggregate(total=Sum("amount_due"))["total"]
    )
    month_allocated = _amount(
        PaymentAllocation.objects.filter(
            schedule__organization=organization, **{f"schedule__{k}": v for k, v in in_month.items()}
        ).aggregate(total=Sum("allocated_amount"))["total"]
    )

    overdue_qs = schedules.filter(is_paid=False, due_date__lt=today, remaining__gt=0).select_related(
        "lease_contract__tenant", "lease_contract__unit"
    )
    overdue = list(overdue_qs.order_by("due_date"))
    aging = []
    for label, low, high in AGING_BUCKETS:
        rows = [s for s in overdue if (today - s.due_date).days >= low and (high is None or (today - s.due_date).days <= high)]
        aging.append({"bucket": label, "amount": sum((s.remaining for s in rows), ZERO), "count": len(rows)})

    upcoming = (
        schedules.filter(is_paid=False, due_date__gte=today, due_date__lte=today + timedelta(days=30), remaining__gt=0)
        .select_related("lease_contract__tenant", "lease_contract__unit")
        .order_by("due_date")[:6]
    )
    by_method = (
        payments.filter(payment_date__date__gte=start)
        .values("payment_method__code", "payment_method__label")
        .annotate(amount=Sum("amount_paid"), count=Count("id"))
        .order_by("-amount")
    )
    recent = payments.select_related("payer", "payment_method").order_by("-payment_date")[:6]

    return {
        "monthly": monthly,
        "period_collected": sum((row["collected"] for row in monthly), ZERO),
        "period_expected": sum((row["expected"] for row in monthly), ZERO),
        "this_month": {
            "expected": month_expected,
            "collected": month_allocated,
            "rate": round(float(month_allocated / month_expected * 100), 1) if month_expected else None,
        },
        "overdue": {
            "amount": sum((s.remaining for s in overdue), ZERO),
            "count": len(overdue),
            "tenants": len({s.lease_contract.tenant_id for s in overdue if s.lease_contract}),
            "aging": aging,
        },
        "late": [_schedule_row(s, today) for s in overdue[:6]],
        "upcoming": [_schedule_row(s, today) for s in upcoming],
        "by_method": [
            {"code": row["payment_method__code"], "label": row["payment_method__label"], "amount": row["amount"], "count": row["count"]}
            for row in by_method
        ],
        "recent_payments": [
            {
                "id": payment.pk,
                "date": payment.payment_date,
                "amount": payment.amount_paid,
                "method": payment.payment_method.label,
                "method_code": payment.payment_method.code,
                "payer": _tenant_name(payment.payer),
            }
            for payment in recent
        ],
    }


def maintenance_section(organization, today, months):
    keys = month_keys(today, months)
    start = keys[0]
    tickets = MaintenanceTicket.objects.filter(unit__building__property__organization=organization)
    by_status = dict(tickets.values_list("status").annotate(count=Count("id")))
    open_tickets = tickets.filter(status__in=OPEN_TICKET_STATUSES)

    created = {
        _key(timezone.localtime(row["month"])): row["count"]
        for row in tickets.filter(created_at__date__gte=start).annotate(month=TruncMonth("created_at")).values("month").annotate(count=Count("id"))
    }
    resolved = {
        _key(timezone.localtime(row["month"])): row["count"]
        for row in tickets.filter(status__in=DONE_TICKET_STATUSES, updated_at__date__gte=start)
        .annotate(month=TruncMonth("updated_at"))
        .values("month")
        .annotate(count=Count("id"))
    }
    done = list(tickets.filter(status__in=DONE_TICKET_STATUSES, updated_at__date__gte=start).values_list("created_at", "updated_at"))
    durations = [(updated - created_at).total_seconds() / 86400 for created_at, updated in done]

    by_category = (
        tickets.filter(created_at__date__gte=start)
        .values("category__label")
        .annotate(count=Count("id"))
        .order_by("-count")
    )
    recent_open = sorted(
        open_tickets.select_related("unit", "category"),
        key=lambda ticket: (PRIORITY_ORDER.get(ticket.priority, 9), ticket.created_at),
    )[:5]
    return {
        "open": open_tickets.count(),
        "urgent_open": open_tickets.filter(priority__in=URGENT_PRIORITIES).count(),
        "by_status": {status: by_status.get(status, 0) for status, _ in MaintenanceTicket.STATUS_CHOICES},
        "monthly": [
            {"month": _key(month), "created": created.get(_key(month), 0), "resolved": resolved.get(_key(month), 0)}
            for month in keys
        ],
        "avg_resolution_days": round(sum(durations) / len(durations), 1) if durations else None,
        "by_category": [{"label": row["category__label"] or "Autre", "count": row["count"]} for row in by_category],
        "recent_open": [
            {
                "id": ticket.pk,
                "unit": ticket.unit.reference,
                "category": ticket.category.label if ticket.category else "",
                "priority": ticket.priority,
                "status": ticket.status,
                "description": ticket.description[:140],
                "age_days": (timezone.now() - ticket.created_at).days,
            }
            for ticket in recent_open
        ],
    }


def listings_section(organization, today, months, request):
    keys = month_keys(today, months)
    start = keys[0]
    listings = Listing.objects.filter(unit__building__property__organization=organization)
    by_status = dict(listings.values_list("status").annotate(count=Count("id")))
    interests = ProspectInterest.objects.filter(listing__in=listings)
    monthly = {
        _key(timezone.localtime(row["month"])): row["count"]
        for row in interests.filter(created_at__date__gte=start).annotate(month=TruncMonth("created_at")).values("month").annotate(count=Count("id"))
    }
    top = (
        listings.filter(status="PUBLISHED")
        .annotate(interests_count=Count("interests", filter=Q(interests__created_at__date__gte=start)))
        .order_by("-interests_count", "-published_at")
        .prefetch_related("photos")[:5]
    )
    recent = interests.select_related("prospect", "listing").order_by("-created_at")[:6]
    return {
        "published": by_status.get("PUBLISHED", 0),
        "drafts": by_status.get("DRAFT", 0),
        "interests_period": interests.filter(created_at__date__gte=start).count(),
        "interests_30d": interests.filter(created_at__date__gte=today - timedelta(days=30)).count(),
        "monthly_interests": [{"month": _key(month), "count": monthly.get(_key(month), 0)} for month in keys],
        "top_listings": [
            {
                "id": listing.pk,
                "title": listing.title,
                "listing_type": listing.listing_type,
                "price": listing.price,
                "interests": listing.interests_count,
                "cover": cover_url(request, listing),
            }
            for listing in top
        ],
        "recent_interests": [
            {
                "id": interest.pk,
                "prospect": interest.prospect.full_name,
                "source": interest.prospect.source,
                "listing_id": interest.listing_id,
                "listing": interest.listing.title,
                "created_at": interest.created_at,
            }
            for interest in recent
        ],
    }


def insights(data, today):
    """Alertes à traiter en priorité, déduites des sections calculées (jamais inventées)."""
    items = []
    finance, leases, maintenance, portfolio, listings = (
        data.get("finance"), data.get("leases"), data.get("maintenance"), data.get("portfolio"), data.get("listings"),
    )
    if finance and finance["overdue"]["count"]:
        count = finance["overdue"]["count"]
        items.append({
            "kind": "overdue", "severity": "danger",
            "title": f"{count} échéance{'s' if count > 1 else ''} en retard",
            "amount": finance["overdue"]["amount"], "href": "/espace/echeances?etat=retard",
        })
    if maintenance and maintenance["urgent_open"]:
        count = maintenance["urgent_open"]
        items.append({
            "kind": "urgent_tickets", "severity": "danger",
            "title": f"{count} ticket{'s' if count > 1 else ''} prioritaire{'s' if count > 1 else ''} ouvert{'s' if count > 1 else ''}",
            "amount": None, "href": "/espace/maintenance",
        })
    if leases and leases["ending_soon"]:
        first = leases["ending_soon"][0]
        count = len(leases["ending_soon"])
        items.append({
            "kind": "leases_ending", "severity": "warning",
            "title": (
                f"{count} baux arrivent à échéance (le premier dans {first['days_left']} j)" if count > 1
                else f"1 bail arrive à échéance dans {first['days_left']} j"
            ),
            "amount": None, "href": f"/espace/baux/{first['id']}",
        })
    if finance and finance["this_month"]["rate"] is not None and today.day > 10 and finance["this_month"]["rate"] < 80:
        items.append({
            "kind": "collection", "severity": "warning",
            "title": f"Recouvrement du mois à {str(finance['this_month']['rate']).replace('.', ',')} %",
            "amount": None, "href": "/espace/echeances?etat=non_payee",
        })
    if portfolio and portfolio["units_by_status"].get("FREE"):
        count = portfolio["units_by_status"]["FREE"]
        items.append({
            "kind": "vacancy", "severity": "info",
            "title": f"{count} lot{'s' if count > 1 else ''} libre{'s' if count > 1 else ''} à louer",
            "amount": None, "href": "/espace/annonces",
        })
    if listings and listings["interests_30d"]:
        count = listings["interests_30d"]
        items.append({
            "kind": "interests", "severity": "success",
            "title": f"{count} demande{'s' if count > 1 else ''} de visite en 30 jours",
            "amount": None, "href": "/espace/annonces",
        })
    return items


def build_dashboard(organization, capabilities, *, months=12, today=None, request=None):
    today = today or timezone.localdate()
    can = capabilities.__contains__
    data = {
        "generated_at": timezone.now(),
        "months": months,
        "portfolio": portfolio_section(organization) if can("property.view") else None,
        "leases": leases_section(organization, today) if can("lease.view") else None,
        "finance": finance_section(organization, today, months) if can("analytics.financial.view") and can("payment.view") else None,
        "maintenance": maintenance_section(organization, today, months) if can("maintenance.ticket.view") else None,
        "listings": listings_section(organization, today, months, request) if can("listing.view") else None,
    }
    data["insights"] = insights(data, today)
    return data

