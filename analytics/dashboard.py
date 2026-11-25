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
from leases.tenants import tenant_names
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


def _schedule_row(schedule, today, name):
    lease = schedule.lease_contract
    return {
        "id": schedule.pk,
        "due_date": schedule.due_date,
        "amount_due": schedule.amount_due,
        "remaining": schedule.remaining,
        "days_late": max(0, (today - schedule.due_date).days),
        "tenant": name(lease.tenant) if lease else "",
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
    name = tenant_names(organization)
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
                "tenant": name(lease.tenant),
                "unit": lease.unit.reference,
                "end_date": lease.end_date,
                "days_left": (lease.end_date - today).days,
                "monthly_rent": lease.rent_amount + lease.charges_amount,
            }
            for lease in ending
        ],
    }


def overdue_by_tenant(overdue, today, name):
    """Échéances en retard regroupées par bail : un locataire par ligne, les plus gros montants d'abord."""
    groups = {}
    for schedule in overdue:
        lease = schedule.lease_contract
        key = lease.pk if lease else None
        group = groups.setdefault(key, {
            "lease_id": key,
            "tenant": name(lease.tenant) if lease else "",
            "unit": lease.unit.reference if lease else "",
            "count": 0,
            "amount": ZERO,
            "days_late": 0,
        })
        group["count"] += 1
        group["amount"] += schedule.remaining
        group["days_late"] = max(group["days_late"], (today - schedule.due_date).days)
    return sorted(groups.values(), key=lambda group: (-group["amount"], -group["days_late"]))


def finance_section(organization, today, months):
    name = tenant_names(organization)
    keys = month_keys(today, months)
    start = keys[0]
    schedules = schedules_with_remaining(organization)
    payments = Payment.objects.cash().filter(organization=organization)

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

    upcoming_qs = schedules.filter(is_paid=False, due_date__gte=today, due_date__lte=today + timedelta(days=30), remaining__gt=0)
    upcoming = upcoming_qs.select_related("lease_contract__tenant", "lease_contract__unit").order_by("due_date")[:6]
    upcoming_total = upcoming_qs.aggregate(total=Sum("remaining"), count=Count("id"))
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
            "payments": payments.filter(payment_date__date__gte=month_start).count(),
        },
        "overdue": {
            "amount": sum((s.remaining for s in overdue), ZERO),
            "count": len(overdue),
            "tenants": len({s.lease_contract.tenant_id for s in overdue if s.lease_contract}),
            "aging": aging,
            "by_tenant": overdue_by_tenant(overdue, today, name)[:6],
        },
        "late": [_schedule_row(s, today, name) for s in overdue[:6]],
        "upcoming": [_schedule_row(s, today, name) for s in upcoming],
        "upcoming_total": _amount(upcoming_total["total"]),
        "upcoming_count": upcoming_total["count"],
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
                "payer": name(payment.payer),
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
    # Lots libres sans annonce en ligne ni en préparation : ce que l'agence peut publier.
    unlisted = (
        Unit.objects.filter(building__property__organization=organization, status="FREE")
        .exclude(listings__status__in=("DRAFT", "PUBLISHED"))
        .order_by("reference")
    )
    return {
        "published": by_status.get("PUBLISHED", 0),
        "unlisted_count": unlisted.count(),
        "unlisted_units": [{"id": unit.pk, "reference": unit.reference} for unit in unlisted[:12]],
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


def _names(names, limit=3):
    """« Ibrahima Kane, Ousmane Faye et 2 autres »."""
    names = [name for name in names if name]
    if len(names) <= limit:
        return ", ".join(names)
    return f"{', '.join(names[:limit])} et {len(names) - limit} autre{'s' if len(names) - limit > 1 else ''}"


def _plural(count, singular, plural=None):
    return f"{count} {singular if count == 1 else (plural or singular + 's')}"


def insights(data, today):
    """
    Points à traiter en priorité, déduits des sections calculées (jamais inventés). Chacun porte un
    titre, une ligne de contexte (`meta`) et une valeur : un montant, un nombre ou une date.
    Le taux de recouvrement n'y figure pas : il est déjà dans les indicateurs du tableau de bord.
    """
    items = []
    finance, leases, maintenance, portfolio, listings = (
        data.get("finance"), data.get("leases"), data.get("maintenance"), data.get("portfolio"), data.get("listings"),
    )

    def add(kind, severity, title, meta, href, amount=None, count=None, date_=None):
        items.append({
            "kind": kind, "severity": severity, "title": title, "meta": meta, "href": href,
            "amount": amount, "count": count, "date": date_,
        })

    if finance and finance["overdue"]["count"]:
        overdue = finance["overdue"]
        add(
            "overdue", "danger",
            f"{_plural(overdue['count'], 'échéance')} en retard",
            _names([group["tenant"] for group in overdue["by_tenant"]]),
            "/espace/loyers?etat=LATE",
            amount=overdue["amount"],
        )
    if maintenance and maintenance["urgent_open"]:
        count = maintenance["urgent_open"]
        urgent = next((t for t in maintenance["recent_open"] if t["priority"] == "URGENT"), None)
        meta = (
            f"Dont une urgence : {(urgent['category'] or 'intervention').lower()} au {urgent['unit']}" if urgent
            else f"Sur {_plural(maintenance['open'], 'ticket ouvert', 'tickets ouverts')}"
        )
        add("urgent_tickets", "warning", f"{_plural(count, 'ticket prioritaire', 'tickets prioritaires')}", meta, "/espace/maintenance", count=count)
    if leases and leases["ending_soon"]:
        first = leases["ending_soon"][0]
        count = len(leases["ending_soon"])
        add(
            "leases_ending", "warning",
            f"{_plural(count, 'bail', 'baux')} à renouveler",
            f"{first['tenant']}, {first['unit']}, dans {first['days_left']} jours",
            f"/espace/baux/{first['id']}" if count == 1 else "/espace/baux",
            count=count, date_=first["end_date"],
        )
    if listings and listings["interests_30d"]:
        count = listings["interests_30d"]
        add(
            "interests", "info",
            f"{_plural(count, 'demande de visite', 'demandes de visite')}",
            f"30 derniers jours, sur {_plural(listings['published'], 'annonce')}",
            "/espace/annonces", count=count,
        )
    if portfolio and portfolio["units_by_status"].get("FREE"):
        count = portfolio["units_by_status"]["FREE"]
        add("vacancy", "info", f"{_plural(count, 'lot libre', 'lots libres')} à louer", "Voir les biens", "/espace/biens", count=count)
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


def nav_counters(organization, capabilities, today=None):
    """
    Compteurs de la barre latérale (biens, échéances en retard, tickets ouverts), en trois requêtes
    simples pour être rafraîchis sur chaque écran. Chacun vaut `None` si le rôle ne voit pas l'écran.
    """
    today = today or timezone.localdate()
    can = capabilities.__contains__
    overdue = None
    if can("payment.schedule.view"):
        overdue = schedules_with_remaining(organization).filter(is_paid=False, due_date__lt=today, remaining__gt=0).count()
    return {
        "properties": Property.objects.filter(organization=organization).count() if can("property.view") else None,
        "overdue_schedules": overdue,
        "open_tickets": (
            MaintenanceTicket.objects.filter(unit__building__property__organization=organization, status__in=OPEN_TICKET_STATUSES).count()
            if can("maintenance.ticket.view") else None
        ),
    }
