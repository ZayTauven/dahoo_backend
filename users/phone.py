import re

from rest_framework import serializers

# Numéro sénégalais à 9 chiffres (mobiles 7x, fixes 3x) saisi sans indicatif.
SENEGAL_LOCAL = re.compile(r"^[37]\d{8}$")
INTERNATIONAL = re.compile(r"^\+\d{8,15}$")


def normalize_phone(value):
    """
    Forme unique d'un numéro : « +221 77 000 00 01 », « 00221770000001 » et « 770000001 »
    deviennent « +221770000001 ». Évite qu'une même personne ait deux comptes.
    Renvoie la valeur nettoyée telle quelle si elle ne ressemble à aucun format connu.
    """
    if value is None:
        return value
    cleaned = re.sub(r"[\s.\-()/]", "", str(value))
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    if SENEGAL_LOCAL.match(cleaned):
        cleaned = "+221" + cleaned
    return cleaned


def validate_phone(value):
    """Normalise et vérifie un numéro saisi dans un formulaire (erreur de validation sinon)."""
    phone = normalize_phone(value)
    if not INTERNATIONAL.match(phone or ""):
        raise serializers.ValidationError("Numéro invalide : utilisez le format international, ex. +221 77 123 45 67.")
    return phone


class PhoneField(serializers.CharField):
    """Champ téléphone normalisé (même forme en base, quelle que soit la saisie)."""

    def to_internal_value(self, data):
        return validate_phone(super().to_internal_value(data))
