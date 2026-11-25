"""E-mails d'abonnement : reçu, échéance, fin d'accès, demande d'offre."""

from django.contrib.auth import get_user_model

from dahoo.french import long_date
from mailing.queue import queue_email
from mailing.team import site, verified
from notifications.services import members_with, money, person_name

User = get_user_model()


def _admins(organization):
    return verified(members_with(organization, "organization.update"))


def _instructions():
    from subscriptions.models import BillingSettings

    return BillingSettings.load().payment_instructions.strip()


def email_subscription_receipt(payment):
    from documents.receipts import share_url

    organization = payment.subscription.organization
    for user in _admins(organization):
        queue_email(
            "subscription_receipt", user.email,
            {
                "first_name": user.first_name, "organization": organization.name, "plan": payment.plan_name,
                "amount": money(payment.amount), "method": payment.method.label, "until": long_date(payment.period_end),
                "url": share_url("subscription", payment.pk),
            },
            organization=organization,
        )


def email_subscription_ending(subscription):
    organization, ends = subscription.organization, subscription.end_date
    for user in _admins(organization):
        queue_email(
            "subscription_ending", user.email,
            {
                "first_name": user.first_name, "organization": organization.name, "plan": subscription.plan.name, "date": long_date(ends),
                "price": money(subscription.price) if subscription.price else "", "instructions": _instructions(), "url": site("/espace/agence"),
            },
            organization=organization, dedupe_key=f"subscription:{subscription.pk}:{user.pk}:{ends:%Y%m%d}:{subscription.days_left}",
        )


def email_subscription_ended(subscription):
    organization, ends = subscription.organization, subscription.end_date
    for user in _admins(organization):
        queue_email(
            "subscription_ended", user.email,
            {
                "first_name": user.first_name, "organization": organization.name, "date": long_date(ends),
                "instructions": _instructions(), "url": site("/espace/agence"),
            },
            organization=organization, dedupe_key=f"subscription-end:{subscription.pk}:{user.pk}:{ends:%Y%m%d}",
        )


def email_plan_request(request):
    organization = request.organization
    for user in verified(User.objects.filter(is_active=True, is_staff=True)):
        queue_email(
            "plan_request", user.email,
            {
                "first_name": user.first_name, "organization": organization.name, "plan": request.plan.name,
                "contact": person_name(request.requested_by), "phone": organization.phone or request.requested_by.phone,
                "message": request.message[:600], "url": site("/plateforme/abonnements"),
            },
        )
