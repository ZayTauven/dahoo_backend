from urllib.parse import quote


def whatsapp_url(phone, message):
    """Lien WhatsApp prérempli : l'agence relit et envoie depuis son propre numéro."""
    digits = "".join(char for char in phone or "" if char.isdigit())
    return f"https://wa.me/{digits}?text={quote(message)}"
