"""
Limitation de débit derrière le front Next.js.

Toutes les requêtes relayées par le serveur Next (connexion, relais de l'espace agence, pages publiques,
formulaires) arrivent à Django avec la même adresse IP : sans correction, tous les visiteurs partageraient
les mêmes compteurs. Le serveur Next s'identifie donc avec une clé partagée (INTERNAL_PROXY_KEY) et transmet
l'IP réelle du visiteur :
- clé valide + IP du visiteur : le compteur est celui de cette IP ;
- clé valide sans IP (lectures publiques rendues côté serveur, mises en cache) : pas de limitation ;
- pas de clé ou clé invalide : comportement standard (IP de la connexion), l'en-tête d'IP est ignoré.
"""

from django.conf import settings
from django.utils.crypto import constant_time_compare
from rest_framework import throttling

PROXY_KEY_HEADER = "HTTP_X_DAHOO_PROXY_KEY"
CLIENT_IP_HEADER = "HTTP_X_DAHOO_CLIENT_IP"


def is_trusted_proxy(request):
    key = getattr(settings, "INTERNAL_PROXY_KEY", "")
    return bool(key) and constant_time_compare(request.META.get(PROXY_KEY_HEADER, ""), key)


def forwarded_client_ip(request):
    """IP du visiteur transmise par le front, uniquement si la requête vient bien du front."""
    if not is_trusted_proxy(request):
        return None
    return request.META.get(CLIENT_IP_HEADER, "").strip() or None


class ProxyAwareThrottleMixin:
    def allow_request(self, request, view):
        if is_trusted_proxy(request) and forwarded_client_ip(request) is None:
            return True
        return super().allow_request(request, view)

    def get_ident(self, request):
        return forwarded_client_ip(request) or super().get_ident(request)


class AnonRateThrottle(ProxyAwareThrottleMixin, throttling.AnonRateThrottle):
    pass


class UserRateThrottle(ProxyAwareThrottleMixin, throttling.UserRateThrottle):
    pass


class ScopedRateThrottle(ProxyAwareThrottleMixin, throttling.ScopedRateThrottle):
    pass
