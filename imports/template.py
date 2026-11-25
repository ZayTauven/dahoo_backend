"""Modèle Excel à remplir : une feuille vide prête à l'emploi, un exemple et le mode d'emploi."""

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from imports.columns import columns_for
from imports.reader import MAX_ROWS, SHEET_NAME

INK = "12153A"
REQUIRED = PatternFill("solid", fgColor="F7941D")
OPTIONAL = PatternFill("solid", fgColor="E7EBF3")
LISTS = {
    "category": '"Appartement,Studio,Maison,Bureau,Local commercial,Terrain"',
    "frequency": '"Mensuel,Trimestriel"',
}
DATES = ("start", "end")
AMOUNTS = ("rent", "charges", "deposit", "arrears")
TEXTS = ("owner_phone", "tenant_phone", "unit")


def _header(sheet, columns):
    for index, column in enumerate(columns, start=1):
        cell = sheet.cell(row=1, column=index, value=column.header)
        cell.font = Font(bold=True, color=INK)
        cell.fill = REQUIRED if column.required else OPTIONAL
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        sheet.column_dimensions[get_column_letter(index)].width = column.width
    sheet.row_dimensions[1].height = 30
    sheet.freeze_panes = "B2"


def build_template(organization):
    columns = columns_for(organization)
    workbook = Workbook()

    sheet = workbook.active
    sheet.title = SHEET_NAME
    _header(sheet, columns)
    for index, column in enumerate(columns, start=1):
        letter = get_column_letter(index)
        if column.key in LISTS:
            rule = DataValidation(type="list", formula1=LISTS[column.key], allow_blank=True)
            sheet.add_data_validation(rule)
            rule.add(f"{letter}2:{letter}{MAX_ROWS + 1}")
        # Format posé d'avance : Excel ne transforme ni les numéros, ni les dates.
        style = "@" if column.key in TEXTS else "DD/MM/YYYY" if column.key in DATES else "#,##0" if column.key in AMOUNTS else None
        if style:
            for line in range(2, MAX_ROWS + 2):
                sheet.cell(row=line, column=index).number_format = style

    example = workbook.create_sheet("Exemple")
    _header(example, columns)
    for line in range(3):
        for index, column in enumerate(columns, start=1):
            example.cell(row=line + 2, column=index, value=column.example[line] or None)

    guide = workbook.create_sheet("Mode d'emploi")
    guide.column_dimensions["A"].width = 24
    guide.column_dimensions["B"].width = 90
    lines = [
        ("Une ligne par lot", f"Remplissez la feuille « {SHEET_NAME} ». {MAX_ROWS} lots au plus par fichier."),
        ("Lot libre", "Laissez vides les colonnes du locataire et du bail."),
        ("Colonnes orange", "Obligatoires. Les autres peuvent rester vides."),
        ("Avant d'enregistrer", "Dahoo contrôle chaque ligne et vous montre les erreurs. Rien n'est créé sans votre accord."),
        ("Renvoyer le fichier", "Sans risque : un lot ou un bail déjà présent n'est pas créé deux fois."),
        ("", ""),
        *[(column.header, column.help) for column in columns],
    ]
    for line, (title, detail) in enumerate(lines, start=1):
        guide.cell(row=line, column=1, value=title).font = Font(bold=True, color=INK)
        guide.cell(row=line, column=2, value=detail).alignment = Alignment(wrap_text=True)

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
