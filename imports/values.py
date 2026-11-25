"""Interprétation d'une cellule telle que les gens la saisissent (« 77 123 45 67 », « 150 000 F », « 5/11/2026 »)."""

import re
from datetime import date, datetime, timedelta
from decimal import Decimal

from users.phone import INTERNATIONAL, normalize_phone

MAX_AMOUNT = Decimal("9999999999")
EXCEL_EPOCH = date(1899, 12, 30)


def text(cell):
    if cell is None or cell.value is None:
        return ""
    value = cell.value
    # « 101 » saisi comme nombre : pas de « 101.0 ».
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return " ".join(str(value).split())


def phone(cell):
    raw = text(cell)
    value = normalize_phone(raw)
    # Excel perd le « + » : 221771234567.
    if re.fullmatch(r"221[37]\d{8}", value or ""):
        value = "+" + value
    if not INTERNATIONAL.match(value or ""):
        raise ValueError(f"Numéro « {raw} » invalide : un seul numéro, ex. 77 123 45 67.")
    return value


def money(cell):
    raw = text(cell)
    value = re.sub(r"(?i)f?\s*cfa|xof|francs?|f$", "", raw).replace("\u00a0", "").replace("\u202f", "").replace(" ", "")
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", value):
        value = re.sub(r"[.,]", "", value)
    if not re.fullmatch(r"\d+([.,]\d+)?", value):
        raise ValueError(f"Montant « {raw} » invalide.")
    amount = Decimal(value.replace(",", ".")).quantize(Decimal("1"))
    if amount > MAX_AMOUNT:
        raise ValueError(f"Montant « {raw} » trop élevé.")
    return amount


def percent(cell):
    raw = text(cell)
    value = raw.replace("%", "").replace(" ", "").replace(",", ".")
    if not re.fullmatch(r"\d+(\.\d+)?", value):
        raise ValueError(f"Pourcentage « {raw} » invalide.")
    rate = Decimal(value)
    # Une cellule au format « % » vaut 0,1 pour 10 %.
    if cell.percent and not raw.endswith("%"):
        rate *= 100
    if rate > 100:
        raise ValueError("La commission ne peut pas dépasser 100 %.")
    return rate.quantize(Decimal("0.01"))


def number(cell):
    raw = text(cell)
    value = re.sub(r"(?i)m2|m²", "", raw).replace(" ", "").replace(",", ".")
    if not re.fullmatch(r"\d+(\.\d+)?", value):
        raise ValueError(f"Nombre « {raw} » invalide.")
    return float(value)


def integer(cell):
    value = number(cell)
    if not value.is_integer():
        raise ValueError(f"Nombre entier attendu, « {text(cell)} » reçu.")
    return int(value)


def day(cell):
    value = cell.value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and 20000 < value < 80000:
        return EXCEL_EPOCH + timedelta(days=int(value))
    raw = text(cell)
    for pattern, order in ((r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})", (3, 2, 1)), (r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T].*)?", (1, 2, 3))):
        match = re.fullmatch(pattern, raw)
        if match:
            try:
                return date(*(int(match[index]) for index in order))
            except ValueError:
                break
    raise ValueError(f"Date « {raw} » invalide : JJ/MM/AAAA.")


def full_name(first, last):
    """(prénom, nom) ; une seule colonne remplie = nom complet, le premier mot est le prénom."""
    if first and last:
        return first, last
    words = (first or last).split()
    if len(words) == 1:
        return words[0], ""
    return words[0], " ".join(words[1:])
