"""
Facturation des abonnements, encaissée hors ligne par l'équipe Dahoo.

Un règlement couvre un nombre d'échéances (mois ou années) et prolonge l'abonnement :
- renouvellement à temps : la nouvelle période suit la précédente, aucun jour payé n'est perdu ;
- renouvellement tardif : la période repart du jour du règlement, les jours sans accès ne sont pas facturés ;
- pendant l'essai : l'accès complet commence tout de suite, la période payée à la fin de l'essai ;
- changement d'offre : l'ancienne s'arrête, ses jours déjà payés sont déduits.
"""

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_DOWN, Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from dahoo.french import long_date
from dahoo.whatsapp import whatsapp_url
from notifications.services import members_with, money
from organizations.models import Organization
from subscriptions.models import BillingSettings, PlanRequest, Subscription, SubscriptionPayment, SubscriptionPlan
from subscriptions.services import ACCESS_TRIAL, build_usage, get_access_status, get_active_subscription, limiting_plan

ZERO = Decimal("0")
MAX_QUANTITY = 36
MAX_BACKDATE_DAYS = 60

BILLING_STATES = [
    ("LAPSED", "À renouveler"),
    ("ENDING", "Se termine bientôt"),
    ("TRIAL_ENDED", "Essai terminé"),
    ("TRIAL", "En essai"),
    ("ACTIVE", "À jour"),
    ("SUSPENDED", "Suspendue"),
]


def add_months(day, months):
    year, month = divmod(day.year * 12 + day.month - 1 + months, 12)
    return date(year, month + 1, min(day.day, calendar.monthrange(year, month + 1)[1]))


def latest_subscription(organization):
    """Dernier abonnement non suspendu : celui qu'un règlement prolonge, même s'il est échu."""
    return (
        Subscription.objects.filter(organization=organization, status="ACTIVE", start_date__lte=timezone.localdate())
        .select_related("plan").order_by("-start_date", "-id").first()
    )


def unused_value(subscription, day):
    """Valeur des jours déjà payés et pas encore écoulés à cette date."""
    total = ZERO
    for payment in subscription.payments.valid().filter(period_end__gte=day):
        length = (payment.period_end - payment.period_start).days + 1
        left = (payment.period_end - max(day, payment.period_start)).days + 1
        total += (payment.amount + payment.credit) * left / length
    return total.quantize(Decimal("1"), rounding=ROUND_DOWN)


@dataclass
class Quote:
    plan: SubscriptionPlan
    quantity: int
    unit_price: Decimal
    gross: Decimal
    credit: Decimal
    discount: Decimal
    amount: Decimal
    period_start: date
    period_end: date
    free_days: int
    renews: Subscription | None
    replaces: Subscription | None
    warnings: list = field(default_factory=list)


def build_quote(organization, *, plan, quantity=1, discount=ZERO, amount=None, paid_on=None):
    today = timezone.localdate()
    paid_on = paid_on or today
    if organization.is_internal:
        raise ValidationError({"detail": "Un compte interne Dahoo n'a pas d'abonnement."})
    if paid_on > today:
        raise ValidationError({"paid_on": "La date du règlement ne peut pas être à venir."})
    if paid_on < today - timedelta(days=MAX_BACKDATE_DAYS):
        raise ValidationError({"paid_on": f"La date du règlement ne peut pas remonter à plus de {MAX_BACKDATE_DAYS} jours."})
    if not 1 <= quantity <= MAX_QUANTITY:
        raise ValidationError({"quantity": f"Entre 1 et {MAX_QUANTITY}."})

    current = latest_subscription(organization)
    running = current if current and (current.end_date is None or current.end_date >= paid_on) else None
    renews = current if current and current.plan_id == plan.pk else None
    replaces = running if running and renews is None else None
    if renews is None and not plan.active:
        raise ValidationError({"plan": "Cette offre n'est plus proposée."})

    # --- Montant
    if plan.billing_type == "COMMISSION":
        if amount is None or amount <= 0:
            raise ValidationError({"amount": "Indiquez le montant de la commission encaissée."})
        if discount:
            raise ValidationError({"discount": "Pas de remise sur une commission : saisissez le montant reçu."})
        gross, unit_price = amount, (amount / quantity).quantize(Decimal("0.01"))
    else:
        unit_price = renews.price if renews and renews.price is not None else plan.price
        if unit_price is None:
            raise ValidationError({"plan": "Cette offre n'a pas de prix."})
        gross = unit_price * quantity
    credit = unused_value(replaces, paid_on) if replaces else ZERO
    if credit > gross:
        raise ValidationError({
            "quantity": f"Le reste déjà payé ({money(credit)}) dépasse le montant dû. Prenez plus de mois, ou changez d'offre à l'échéance."
        })
    if discount < 0 or discount > gross - credit:
        raise ValidationError({"discount": f"La remise ne peut pas dépasser {money(gross - credit)}."})

    # --- Période
    trial_end = timezone.localdate(organization.trial_ends_at)
    free_days = 0
    if running and renews:
        paid_until = running.end_date or max(
            (p.period_end for p in running.payments.valid()), default=paid_on - timedelta(days=1)
        )
        start = max(paid_on, paid_until + timedelta(days=1))
    elif running is None and trial_end > paid_on and organization.trial_ends_at > timezone.now():
        start = trial_end
        free_days = (trial_end - paid_on).days
    else:
        start = paid_on
    end = add_months(start, plan.months * quantity) - timedelta(days=1)

    warnings = []
    for usage in build_usage(organization, plan):
        if usage["limit"] is not None and usage["used"] > usage["limit"]:
            warnings.append(
                f"{usage['label']} : {usage['used']} déjà créés pour {usage['limit']} permis. Rien n'est supprimé, mais les ajouts seront bloqués."
            )
    if end < today:
        warnings.append("La période couverte est déjà passée : elle ne rouvre pas l'accès.")
    return Quote(
        plan=plan, quantity=quantity, unit_price=unit_price, gross=gross, credit=credit, discount=discount,
        amount=gross - credit - discount, period_start=start, period_end=end, free_days=free_days, renews=renews, replaces=replaces, warnings=warnings,
    )


@transaction.atomic
def record_payment(organization, *, user, method, reference="", note="", paid_on=None, **terms):
    """Enregistre un règlement et ouvre, prolonge ou remplace l'abonnement."""
    from mailing.subscriptions import email_subscription_receipt

    organization = Organization.objects.select_for_update().get(pk=organization.pk)
    paid_on = paid_on or timezone.localdate()
    reference = reference.strip()
    if reference and SubscriptionPayment.objects.valid().filter(method=method, reference__iexact=reference).exists():
        raise ValidationError({"reference": "Un règlement porte déjà cette référence."})
    quote = build_quote(organization, paid_on=paid_on, **terms)

    subscription, opens, previous_end = quote.renews, False, None
    if quote.replaces:
        replaced_end = quote.replaces.end_date
        quote.replaces.status = "EXPIRED"
        quote.replaces.end_date = max(quote.replaces.start_date, paid_on - timedelta(days=1))
        quote.replaces.save(update_fields=["status", "end_date"])
    else:
        replaced_end = None
    if subscription is None:
        opens = True
        subscription = Subscription.objects.create(
            organization=organization, plan=quote.plan, start_date=paid_on, end_date=quote.period_end,
        )
    else:
        previous_end = subscription.end_date
        subscription.end_date = quote.period_end
        subscription.save(update_fields=["end_date"])

    payment = SubscriptionPayment.objects.create(
        subscription=subscription, plan_name=quote.plan.name, months=quote.plan.months, quantity=quote.quantity,
        unit_price=quote.unit_price, credit=quote.credit, discount=quote.discount, amount=quote.amount,
        period_start=quote.period_start, period_end=quote.period_end, paid_on=paid_on, method=method,
        reference=reference, note=note.strip(), opens_subscription=opens, previous_end_date=previous_end,
        replaced_subscription=quote.replaces, replaced_end_date=replaced_end, recorded_by=user,
    )
    PlanRequest.objects.filter(organization=organization, status="OPEN").update(status="HANDLED", handled_at=timezone.now())
    email_subscription_receipt(payment)
    return payment


@transaction.atomic
def cancel_payment(payment, *, user, reason):
    """Annule le dernier règlement de l'agence et rétablit l'abonnement d'avant."""
    organization = Organization.objects.select_for_update().get(pk=payment.subscription.organization_id)
    payment = SubscriptionPayment.objects.select_for_update(of=("self",)).select_related("subscription", "replaced_subscription").get(pk=payment.pk)
    if payment.cancelled_at:
        raise ValidationError({"detail": "Ce règlement est déjà annulé."})
    if SubscriptionPayment.objects.valid().filter(subscription__organization=organization, pk__gt=payment.pk).exists():
        raise ValidationError({"detail": "Annulez d'abord le règlement le plus récent de cette agence."})
    subscription = payment.subscription
    # Une fin corrigée à la main depuis n'est pas écrasée.
    if payment.opens_subscription:
        subscription.status = "EXPIRED"
        subscription.save(update_fields=["status"])
    elif subscription.end_date == payment.period_end:
        subscription.end_date = payment.previous_end_date
        subscription.save(update_fields=["end_date"])
    if payment.replaced_subscription:
        payment.replaced_subscription.status = "ACTIVE"
        payment.replaced_subscription.end_date = payment.replaced_end_date
        payment.replaced_subscription.save(update_fields=["status", "end_date"])
    payment.cancelled_at, payment.cancelled_by, payment.cancel_reason = timezone.now(), user, reason
    payment.save(update_fields=["cancelled_at", "cancelled_by", "cancel_reason"])
    return payment


# --- Suivi par l'équipe Dahoo


def billing_state(organization):
    if not organization.is_active:
        return "SUSPENDED"
    current = get_active_subscription(organization)
    if current:
        return "ENDING" if current.state == "ENDING" else "ACTIVE"
    if get_access_status(organization) == ACCESS_TRIAL:
        return "TRIAL"
    return "LAPSED" if organization.subscriptions.exists() else "TRIAL_ENDED"


def monthly_value(subscription):
    """Revenu mensuel d'un abonnement au prix convenu (une commission n'est pas prévisible)."""
    plan, price = subscription.plan, subscription.price
    if price is None or plan.billing_type == "COMMISSION":
        return ZERO
    return (price / plan.months).quantize(Decimal("1"))


def billing_summary(organization):
    """Où en est une agence : offre, échéance, consommation, dernier règlement."""
    state = billing_state(organization)
    subscription = get_active_subscription(organization) or (latest_subscription(organization) if state != "TRIAL" else None)
    plan, _ = limiting_plan(organization)
    last = (
        SubscriptionPayment.objects.valid().filter(subscription__organization=organization)
        .select_related("method").order_by("-paid_on", "-id").first()
    )
    return {
        "organization": organization,
        "state": state,
        "subscription": subscription,
        "monthly_value": monthly_value(subscription) if subscription and state in ("ACTIVE", "ENDING") else ZERO,
        "usage": build_usage(organization, plan),
        "last_payment": last,
        "request": PlanRequest.objects.filter(organization=organization, status="OPEN").select_related("plan", "requested_by").first(),
    }


def _deadline(row):
    if row["subscription"] is not None:
        return row["subscription"].end_date or date.max
    return timezone.localdate(row["organization"].trial_ends_at)


def build_billing_board():
    order = {code: index for index, (code, _) in enumerate(BILLING_STATES)}
    organizations = Organization.objects.filter(is_internal=False).order_by("name")
    rows = sorted((billing_summary(org) for org in organizations), key=lambda row: (row["request"] is None, order[row["state"]], _deadline(row), row["organization"].name))
    today = timezone.localdate()
    payments = SubscriptionPayment.objects.valid()
    to_renew = [row for row in rows if row["state"] in ("LAPSED", "ENDING")]
    return {
        "mrr": sum((row["monthly_value"] for row in rows), ZERO),
        "collected_month": sum((p.amount for p in payments.filter(paid_on__year=today.year, paid_on__month=today.month)), ZERO),
        "collected_year": sum((p.amount for p in payments.filter(paid_on__year=today.year)), ZERO),
        "subscribers": sum(row["state"] in ("ACTIVE", "ENDING") for row in rows),
        "to_renew": len(to_renew),
        "to_renew_amount": sum((row["subscription"].price or ZERO for row in to_renew if row["subscription"]), ZERO),
        "trials": sum(row["state"] == "TRIAL" for row in rows),
        "requests": sum(row["request"] is not None for row in rows),
        "rows": rows,
    }


def price_label(plan, price=None):
    if plan.billing_type == "COMMISSION":
        return "à la commission"
    value = plan.price if price is None else price
    if value is None:
        return ""
    return f"{money(value)} par {'an' if plan.billing_type == 'YEARLY' else 'mois'}"


def billing_reminder(organization):
    """Message d'échéance à envoyer par WhatsApp depuis le téléphone de l'équipe Dahoo."""
    summary = billing_summary(organization)
    state, subscription = summary["state"], summary["subscription"]
    if state in ("TRIAL", "TRIAL_ENDED"):
        ends = long_date(timezone.localdate(organization.trial_ends_at))
        lines = [f"Votre essai Dahoo se termine le {ends}." if state == "TRIAL" else f"Votre essai Dahoo s'est terminé le {ends}."]
    elif subscription is None or subscription.end_date is None:
        raise ValidationError({"detail": "Cet abonnement n'a pas d'échéance."})
    else:
        verb = "s'est terminé" if state == "LAPSED" else "se termine"
        price = price_label(subscription.plan, subscription.price)
        lines = [f"Votre abonnement Dahoo, offre {subscription.plan.name}{f' ({price})' if price else ''}, {verb} le {long_date(subscription.end_date)}."]
    if state in ("LAPSED", "TRIAL_ENDED"):
        lines.append("Votre espace est en lecture seule : rien n'est supprimé, tout revient dès le règlement.")
    instructions = BillingSettings.load().payment_instructions.strip()
    if instructions:
        lines.append(f"Pour régler : {instructions}")
    # WhatsApp ne joint pas une ligne fixe : à défaut d'un mobile d'agence, celui d'un administrateur.
    contact = members_with(organization, "organization.update").first()
    phone = organization.phone
    if contact and not phone.startswith("+2217"):
        phone = contact.phone
    message = "\n".join([f"Bonjour {organization.name},", *lines, "L'équipe Dahoo"]).replace("\u202f", " ").replace("\u00a0", " ")
    return {"message": message, "phone": phone, "whatsapp_url": whatsapp_url(phone, message) if phone else ""}


# --- Demandes d'offre


def request_plan(organization, *, user, plan, message=""):
    """Une seule demande ouverte par agence : une nouvelle remplace la précédente."""
    from mailing.subscriptions import email_plan_request
    from notifications.services import notify_platform_admins, person_name

    with transaction.atomic():
        Organization.objects.select_for_update().get(pk=organization.pk)
        PlanRequest.objects.filter(organization=organization, status="OPEN").delete()
        request = PlanRequest.objects.create(organization=organization, plan=plan, requested_by=user, message=message.strip())
    notify_platform_admins(
        kind="PLAN_REQUEST", title=f"{organization.name} demande l'offre {plan.name}",
        body=" · ".join(part for part in (person_name(user), request.message[:120]) if part), link="/plateforme/abonnements",
    )
    email_plan_request(request)
    return request

