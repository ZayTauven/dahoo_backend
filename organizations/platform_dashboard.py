"""
Tableau de bord de l'espace plateforme (équipe Dahoo) : parc d'agences, essais, abonnements,
revenu récurrent, demandes de démo, activité du portail. Calculé à la volée (quelques dizaines
d'agences) ; réservé aux administrateurs de la plateforme (voir IsPlatformAdmin).
"""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from analytics.dashboard import month_keys
from listings.models import Listing, ProspectInterest
from listings.photos import media_url
from organizations.models import Membership, Organization
from payments.models import Payment
from properties.models import Unit
from public.models import DemoRequest
from subscriptions.models import Subscription
from subscriptions.services import ACCESS_ACTIVE, ACCESS_EXPIRED, ACCESS_TRIAL, get_access_status

ZERO = Decimal("0")
TRIAL_WARNING_DAYS = 14


def _key(value):
    return timezone.localtime(value).strftime("%Y-%m") if timezone.is_aware(value) else value.strftime("%Y-%m")


def _monthly_equivalent(subscription):
    """Revenu mensuel d'un abonnement : prix mensuel, ou annuel / 12 (les commissions ne sont pas prévisibles)."""
    plan = subscription.plan
    if plan.price is None:
        return ZERO
    if plan.billing_type == "MONTHLY":
        return plan.price
    if plan.billing_type == "YEARLY":
        return (plan.price / 12).quantize(Decimal("1"))
    return ZERO


def _status(organization):
    if not organization.is_active:
        return "SUSPENDED"
    return get_access_status(organization)


def build_platform_dashboard(*, months=12, request=None):
    today = timezone.localdate()
    now = timezone.now()
    keys = month_keys(today, months)
    start = keys[0]

    organizations = list(
        Organization.objects.annotate(
            members=Count("memberships", filter=Q(memberships__is_active=True), distinct=True),
            listings_published=Count(
                "properties__buildings__units__listings",
                filter=Q(properties__buildings__units__listings__status="PUBLISHED"),
                distinct=True,
            ),
            units_total=Count("properties__buildings__units", distinct=True),
        ).order_by("name")
    )
    agencies = [org for org in organizations if not org.is_internal]
    statuses = {org.pk: _status(org) for org in agencies}
    by_status = {status: 0 for status in (ACCESS_ACTIVE, ACCESS_TRIAL, ACCESS_EXPIRED, "SUSPENDED")}
    for status in statuses.values():
        by_status[status] += 1

    ending = sorted(
        (org for org in agencies if statuses[org.pk] == ACCESS_TRIAL and org.trial_ends_at <= now + timedelta(days=TRIAL_WARNING_DAYS)),
        key=lambda org: org.trial_ends_at,
    )

    signups = {
        _key(row["month"]): row["count"]
        for row in Organization.objects.filter(is_internal=False, created_at__date__gte=start)
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(count=Count("id"))
    }
    demos = DemoRequest.objects.all()
    demo_monthly = {
        _key(row["month"]): row["count"]
        for row in demos.filter(created_at__date__gte=start).annotate(month=TruncMonth("created_at")).values("month").annotate(count=Count("id"))
    }

    active_subscriptions = list(
        Subscription.objects.filter(status="ACTIVE", start_date__lte=today)
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=today))
        .select_related("plan", "organization")
    )
    by_plan = {}
    for subscription in active_subscriptions:
        entry = by_plan.setdefault(subscription.plan.name, {"plan": subscription.plan.name, "count": 0, "mrr": ZERO})
        entry["count"] += 1
        entry["mrr"] += _monthly_equivalent(subscription)

    published = Listing.objects.filter(status="PUBLISHED")
    interests = ProspectInterest.objects.all()
    payments_30d = Payment.objects.filter(payment_date__gte=now - timedelta(days=30))

    top = sorted(agencies, key=lambda org: (org.listings_published, org.units_total, org.members), reverse=True)[:6]

    return {
        "generated_at": now,
        "months": months,
        "agencies": {
            "total": len(agencies),
            "by_status": by_status,
            "members": Membership.objects.filter(is_active=True, organization__is_internal=False).count(),
            "cities": len({org.city.strip().lower() for org in agencies if org.city}),
        },
        "trials_ending": [
            {
                "id": org.pk,
                "name": org.name,
                "city": org.city,
                "days_left": max(0, (org.trial_ends_at.date() - today).days),
                "members": org.members,
                "listings": org.listings_published,
            }
            for org in ending
        ],
        "monthly": [
            {"month": key.strftime("%Y-%m"), "signups": signups.get(key.strftime("%Y-%m"), 0), "demo_requests": demo_monthly.get(key.strftime("%Y-%m"), 0)}
            for key in keys
        ],
        "subscriptions": {
            "active": len(active_subscriptions),
            "mrr": sum((_monthly_equivalent(s) for s in active_subscriptions), ZERO),
            "by_plan": sorted(by_plan.values(), key=lambda entry: -entry["count"]),
        },
        "demo_requests": {
            "total": demos.count(),
            "pending": demos.filter(handled=False).count(),
            "last_30d": demos.filter(created_at__gte=now - timedelta(days=30)).count(),
            "recent_pending": [
                {
                    "id": demo.pk,
                    "agency_name": demo.agency_name,
                    "contact_name": demo.contact_name,
                    "city": demo.city,
                    "units_range": demo.units_range,
                    "created_at": demo.created_at,
                }
                for demo in demos.filter(handled=False).order_by("-created_at")[:5]
            ],
        },
        "portal": {
            "listings_published": published.count(),
            "listings_rent": published.filter(listing_type="RENT").count(),
            "listings_sale": published.filter(listing_type="SALE").count(),
            "interests_30d": interests.filter(created_at__gte=now - timedelta(days=30)).count(),
            "units_managed": Unit.objects.filter(building__property__organization__is_internal=False).count(),
            "payments_30d_amount": payments_30d.aggregate(total=Sum("amount_paid"))["total"] or ZERO,
            "payments_30d_count": payments_30d.count(),
        },
        "top_agencies": [
            {
                "id": org.pk,
                "name": org.name,
                "city": org.city,
                "logo": media_url(request, org.logo.name) if org.logo else None,
                "status": statuses[org.pk],
                "members": org.members,
                "units": org.units_total,
                "listings": org.listings_published,
            }
            for org in top
        ],
    }
