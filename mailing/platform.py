from django.contrib.auth import get_user_model

from mailing.queue import queue_email
from mailing.team import site, verified

User = get_user_model()


def email_demo_request(demo):
    context = {
        "agency": demo.agency_name, "contact": demo.contact_name, "phone": demo.phone, "email": demo.email,
        "city": demo.city, "units": demo.units_range, "message": demo.message[:600],
    }
    for user in verified(User.objects.filter(is_active=True, is_staff=True)):
        queue_email("demo_request", user.email, {"first_name": user.first_name, **context, "url": site("/plateforme/demandes")})
    queue_email("demo_received", demo.email, {"name": demo.contact_name, "phone": demo.phone}, dedupe_key=f"demo:{demo.pk}")
