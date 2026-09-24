from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

from users.phone import normalize_phone

User = get_user_model()


class PhoneBackend(ModelBackend):
    def authenticate(self, request, phone=None, password=None, username=None, **kwargs):
        # L'API transmet « phone » ; l'admin Django transmet l'identifiant sous le nom « username ».
        phone = normalize_phone(phone or username)
        if not phone or password is None:
            return None

        try:
            user = User.objects.get(phone=phone)
        except User.DoesNotExist:
            # Même coût qu'un vrai contrôle : le temps de réponse ne révèle pas si le numéro existe.
            User().set_password(password)
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
