"""Mise en forme française des documents : mois, montants en lettres."""

from decimal import ROUND_HALF_UP, Decimal

MONTHS = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]

_UNITS = [
    "zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix",
    "onze", "douze", "treize", "quatorze", "quinze", "seize",
]
_TENS = {2: "vingt", 3: "trente", 4: "quarante", 5: "cinquante", 6: "soixante", 8: "quatre-vingt"}


def month_label(day):
    """« novembre 2026 »"""
    return f"{MONTHS[day.month - 1]} {day.year}"


def long_date(day):
    """« 5 novembre 2026 » (« 1er » pour le premier du mois)"""
    return f"{'1er' if day.day == 1 else day.day} {month_label(day)}"


def _below_hundred(n):
    if n < 17:
        return _UNITS[n]
    if n < 20:
        return f"dix-{_UNITS[n - 10]}"
    tens, unit = divmod(n, 10)
    if tens in (7, 9):  # soixante-dix, quatre-vingt-dix
        tens, unit = tens - 1, unit + 10
    word = _TENS[tens]
    if unit == 0:
        return word + ("s" if tens == 8 else "")
    if unit in (1, 11) and tens != 8:
        return f"{word} et {_below_hundred(unit)}"
    return f"{word}-{_below_hundred(unit)}"


def _below_thousand(n):
    hundreds, rest = divmod(n, 100)
    if not hundreds:
        return _below_hundred(rest)
    head = "cent" if hundreds == 1 else f"{_UNITS[hundreds]} cent"
    if not rest:
        return head + ("s" if hundreds > 1 else "")
    return f"{head} {_below_hundred(rest)}"


def number_to_words(n):
    """Entier positif en toutes lettres : 151000 → « cent cinquante et un mille »."""
    if n < 1000:
        return _below_thousand(n)
    parts = []
    for value, name in ((10**9, "milliard"), (10**6, "million")):
        count, n = divmod(n, value)
        if count:
            parts.append(f"{_below_thousand(count)} {name}{'s' if count > 1 else ''}")
    thousands, n = divmod(n, 1000)
    if thousands:
        # « mille » est invariable, et « cent » / « quatre-vingt » y perdent leur « s ».
        head = _below_thousand(thousands)
        if head.endswith(("cents", "quatre-vingts")):
            head = head[:-1]
        parts.append("mille" if thousands == 1 else f"{head} mille")
    if n:
        parts.append(_below_thousand(n))
    return " ".join(parts)


def amount_in_words(amount):
    """« cent cinquante mille francs CFA »"""
    value = int(Decimal(amount).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    words = number_to_words(value)
    # « un million de francs », mais « un million cinq cents francs ».
    link = "de " if words.endswith(("million", "millions", "milliard", "milliards")) else ""
    return f"{words} {link}franc{'s' if value > 1 else ''} CFA"
