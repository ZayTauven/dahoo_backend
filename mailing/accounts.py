"""E-mails du compte : bienvenue, confirmation d'adresse, mot de passe."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import signing
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework.exceptions import ValidationError

from mailing.queue import queue_email

User = get_user_model()

CONFIRM_SALT = "dahoo.email-confirm"
CONFIRM_MAX_AGE = 3 * 24 * 3600


def confirm_url(user, email):
    token = signing.dumps({"u": user.pk, "e": email}, salt=CONFIRM_SALT)
    return f"{settings.PUBLIC_SITE_URL}/confirmer-email/{token}"


def send_confirmation(user, email):
    return queue_email("email_confirm", email, {"first_name": user.first_name, "email": email, "url": confirm_url(user, email)})


def confirm_email(token):
    """Enregistre l'adresse confirmée : la seule à recevoir un lien de mot de passe ou des données d'agence."""
    try:
        data = signing.loads(token, salt=CONFIRM_SALT, max_age=CONFIRM_MAX_AGE)
    except signing.BadSignature:
        raise ValidationError({"detail": "Ce lien n'est pas valide ou a expiré."})
    user = User.objects.filter(pk=data["u"], is_active=True).first()
    if user is None:
        raise ValidationError({"detail": "Ce compte n'existe plus."})
    user.email, user.email_verified_at = data["e"], timezone.now()
    user.save(update_fields=["email", "email_verified_at"])
    return user


def send_welcome(user, organization):
    if not user.email:
        return None
    return queue_email("account_welcome", user.email, {
        "first_name": user.first_name, "organization": organization.name, "phone": user.phone,
        "url": confirm_url(user, user.email),
    })


def verified_email(user):
    return user.email if user.email and user.email_verified_at else ""


def send_password_reset(user):
    email = verified_email(user)
    if not (email and user.is_active and user.has_usable_password()):
        return None
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    return queue_email("password_reset", email, {
        "first_name": user.first_name, "minutes": settings.PASSWORD_RESET_TIMEOUT // 60,
        "url": f"{settings.PUBLIC_SITE_URL}/nouveau-mot-de-passe?id={uid}&jeton={token}",
    })


def user_from_reset(uid, token):
    try:
        user = User.objects.get(pk=force_str(urlsafe_base64_decode(uid)), is_active=True)
    except (User.DoesNotExist, ValueError, TypeError, OverflowError):
        user = None
    if user is None or not default_token_generator.check_token(user, token):
        raise ValidationError({"detail": "Ce lien n'est plus valable : demandez-en un nouveau."})
    return user


def send_password_changed(user):
    return queue_email("password_changed", verified_email(user), {
        "first_name": user.first_name, "when": f"{timezone.localtime():%d/%m/%Y à %H:%M}",
    })


def send_password_temporary(user, author):
    return queue_email("password_temporary", verified_email(user), {"first_name": user.first_name, "author": author})
