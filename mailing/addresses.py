from django.conf import settings

# Domaines réservés (RFC 2606 et 6761) : jamais de vraie boîte derrière.
RESERVED = ("example.com", "example.org", "example.net", "localhost")
RESERVED_SUFFIXES = (".test", ".example", ".invalid", ".localhost", ".local")


def is_deliverable(email):
    """Adresse à laquelle on accepte d'écrire : ni vide, ni fictive, ni bloquée (comptes de démonstration)."""
    domain = (email or "").rpartition("@")[2].lower()
    if "." not in domain or domain in RESERVED or domain.endswith(RESERVED_SUFFIXES):
        return False
    return not any(domain == blocked or domain.endswith(f".{blocked}") for blocked in settings.EMAIL_BLOCKED_DOMAINS)
