"""Lecture du fichier envoyé (Excel .xlsx ou CSV) : renvoie les lignes brutes, sans les interpréter."""

import csv
import io
import zipfile
from dataclasses import dataclass, field

from openpyxl import load_workbook
from rest_framework.exceptions import ValidationError

from imports.columns import BY_KEY, HEADERS, normalize

MAX_FILE_SIZE = 2 * 1024 * 1024
MAX_UNZIPPED = 40 * 1024 * 1024
MAX_ROWS = 500
# Un tableur garde parfois des milliers de lignes vides mises en forme : on s'arrête après un long blanc.
MAX_BLANK_RUN = 100
HEADER_SEARCH = 15
SHEET_NAME = "Parc locatif"


@dataclass(frozen=True)
class Cell:
    value: object
    percent: bool = False


@dataclass
class RawRow:
    line: int
    cells: dict = field(default_factory=dict)


@dataclass
class RawFile:
    rows: list
    ignored_columns: list


def _fail(message):
    raise ValidationError({"file": message})


def read_file(upload):
    name = (upload.name or "").lower()
    if upload.size > MAX_FILE_SIZE:
        _fail("Fichier trop lourd (2 Mo au plus).")
    content = upload.read()
    if name.endswith(".xlsx"):
        return _parse(_xlsx_rows(content))
    if name.endswith((".csv", ".txt")):
        return _parse(_csv_rows(content))
    if name.endswith(".xls"):
        _fail("Ancien format Excel : enregistrez le fichier au format .xlsx puis renvoyez-le.")
    _fail("Format non reconnu : envoyez un fichier Excel (.xlsx) ou CSV.")


def _xlsx_rows(content):
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            # Archive piégée : quelques kilo-octets qui se déplient en giga-octets.
            if sum(entry.file_size for entry in archive.infolist()) > MAX_UNZIPPED:
                _fail("Fichier trop volumineux une fois ouvert.")
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except ValidationError:
        raise
    except Exception:  # noqa: BLE001 - archive abîmée, fichier protégé, format détourné…
        _fail("Ce fichier Excel n'a pas pu être ouvert. Vérifiez qu'il n'est pas protégé par un mot de passe.")
    sheet = workbook[SHEET_NAME] if SHEET_NAME in workbook.sheetnames else workbook.worksheets[0]
    try:
        for number, row in enumerate(sheet.iter_rows(), start=1):
            yield number, [Cell(cell.value, "%" in str(getattr(cell, "number_format", "") or "")) for cell in row]
    finally:
        workbook.close()


def _csv_rows(content):
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        _fail("Encodage du fichier non reconnu.")
    sample = text[:4000]
    delimiter = max(";,\t", key=sample.count)
    try:
        for number, row in enumerate(csv.reader(io.StringIO(text), delimiter=delimiter), start=1):
            yield number, [Cell(value) for value in row]
    except csv.Error:
        _fail("Ce fichier CSV n'a pas pu être lu.")


def _is_blank(cell):
    return cell.value is None or str(cell.value).strip() == ""


def _match_header(cells):
    """{index: clé} si la ligne est l'en-tête (elle porte au moins « Bien » et « Lot »), sinon None."""
    mapping, ignored = {}, []
    for index, cell in enumerate(cells):
        if _is_blank(cell):
            continue
        key = HEADERS.get(normalize(cell.value))
        if key is None:
            ignored.append(str(cell.value).strip()[:60])
        elif key in mapping.values():
            return None, [], key
        else:
            mapping[index] = key
    if {"property", "unit"} <= set(mapping.values()):
        return mapping, ignored, None
    return None, [], None


def _parse(rows):
    mapping, ignored, parsed, blanks = None, [], [], 0
    for number, cells in rows:
        if mapping is None:
            mapping, ignored, duplicate = _match_header(cells)
            if duplicate and number <= HEADER_SEARCH:
                _fail(f"La colonne « {BY_KEY[duplicate].header} » apparaît deux fois.")
            if mapping is None and number >= HEADER_SEARCH:
                break
            continue
        raw = RawRow(number, {key: cells[index] for index, key in mapping.items() if index < len(cells) and not _is_blank(cells[index])})
        if not raw.cells:
            blanks += 1
            if blanks >= MAX_BLANK_RUN:
                break
            continue
        blanks = 0
        parsed.append(raw)
        if len(parsed) > MAX_ROWS:
            _fail(f"{MAX_ROWS} lots au plus par fichier : découpez-le en plusieurs envois.")
    if mapping is None:
        _fail("Colonnes non reconnues : il faut au moins « Bien » et « Lot ». Partez du modèle Dahoo.")
    if not parsed:
        _fail("Le fichier ne contient aucun lot.")
    return RawFile(parsed, ignored)
