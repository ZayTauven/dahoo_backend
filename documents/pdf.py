"""Mise en page commune des documents PDF remis aux locataires et aux bailleurs (ReportLab)."""

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from xml.sax.saxutils import escape

from notifications.services import money as _money

INK = colors.HexColor("#1B1D36")
MUTED = colors.HexColor("#5F6377")
LINE = colors.HexColor("#D9DBE4")
TINT = colors.HexColor("#F4F5F9")

BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=9.5, leading=14, textColor=INK)
MUTE = ParagraphStyle("mute", parent=BODY, fontSize=8.5, leading=12, textColor=MUTED)
STRONG = ParagraphStyle("strong", parent=BODY, fontName="Helvetica-Bold")
RIGHT = ParagraphStyle("right", parent=BODY, alignment=TA_RIGHT)
RIGHT_STRONG = ParagraphStyle("right-strong", parent=STRONG, alignment=TA_RIGHT)
RIGHT_MUTE = ParagraphStyle("right-mute", parent=MUTE, alignment=TA_RIGHT)
TITLE = ParagraphStyle("title", parent=BODY, fontName="Helvetica-Bold", fontSize=18, leading=22)
SECTION = ParagraphStyle("section", parent=STRONG, fontSize=10.5, leading=14)

WIDTH = A4[0] - 40 * mm


def money(amount):
    """Montant lisible par les polices PDF standard (espace insécable simple)."""
    return _money(amount).replace("\u202f", "\u00a0")


def number(amount):
    """Montant sans devise, pour les tableaux serrés (la devise est dans l'en-tête)."""
    return money(amount).replace("\u00a0F\u00a0CFA", "").replace(" F CFA", "")


def phone(value):
    """« +221775550108 » → « +221 77 555 01 08 »"""
    if len(value) == 13 and value.startswith("+221"):
        return f"+221 {value[4:6]} {value[6:9]} {value[9:11]} {value[11:]}"
    return value


def text(value, style=BODY):
    """Paragraphe d'un texte saisi (échappé : un « & » ou un « < » ne casse pas le document)."""
    return Paragraph(escape(str(value or "")).replace("\n", "<br/>"), style)


def _logo(organization):
    """Logo de l'agence, s'il est lisible ; un fichier absent n'empêche pas d'émettre le document."""
    if not organization.logo:
        return None
    try:
        with organization.logo.open("rb") as file:
            data = BytesIO(file.read())
        width, height = ImageReader(data).getSize()
        data.seek(0)
    except Exception:  # noqa: BLE001 - fichier manquant ou image illisible
        return None
    ratio = min(38 * mm / width, 16 * mm / height)
    return Image(data, width=width * ratio, height=height * ratio, hAlign="LEFT")


def header(organization, *, title, reference_number, issued):
    contact = " · ".join(part for part in (phone(organization.phone), organization.email) if part)
    place = ", ".join(part for part in (organization.address.replace("\n", " ").strip(), organization.city) if part)
    identity = [part for part in (_logo(organization), text(organization.name, STRONG)) if part]
    identity += [text(line, MUTE) for line in (place, contact) if line]
    reference = [text(title, ParagraphStyle("t", parent=TITLE, alignment=TA_RIGHT)), text(f"N° {reference_number}", RIGHT_MUTE), text(f"Émise le {issued}" if title.startswith("Quittance") else f"Émis le {issued}", RIGHT_MUTE)]
    table = Table([[identity, reference]], colWidths=[WIDTH * 0.52, WIDTH * 0.48])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("LINEBELOW", (0, 0), (-1, -1), 0.8, INK),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    return [table, Spacer(1, 9 * mm)]


def facts(*columns):
    """Colonnes « libellé / valeur » : parties, logement, période."""
    cells = [[text(label, MUTE)] + [text(line, STRONG if i == 0 else BODY) for i, line in enumerate(lines) if line] for label, lines in columns]
    table = Table([cells], colWidths=[WIDTH / len(cells)] * len(cells))
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return [table, Spacer(1, 8 * mm)]


def lines(head, rows, *, total=None, widths=None, numeric=1):
    """Tableau de montants : les `numeric` dernières colonnes sont alignées à droite."""
    count = len(head)

    def cells(values, left, right):
        return [text(value, right if index >= count - numeric else left) for index, value in enumerate(values)]

    data = [cells(head, MUTE, RIGHT_MUTE)] + [cells(row, BODY, RIGHT) for row in rows]
    if total:
        data.append(cells(total, STRONG, RIGHT_STRONG))
    table = Table(data, colWidths=[WIDTH * share for share in widths] if widths else None, repeatRows=1)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, INK),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    if total:
        style.append(("BACKGROUND", (0, -1), (-1, -1), TINT))
    table.setStyle(TableStyle(style))
    return [table, Spacer(1, 6 * mm)]


def render(title, story, *, footer):
    """Document A4 ; `footer` est répété en bas de chaque page."""
    buffer = BytesIO()

    def draw_footer(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(20 * mm, 12 * mm, footer)
        canvas.drawRightString(A4[0] - 20 * mm, 12 * mm, f"Page {document.page}")
        canvas.restoreState()

    document = SimpleDocTemplate(
        buffer, pagesize=A4, title=title, author=footer,
        # Le cadre ReportLab ajoute 6 points de marge : retirés ici pour aligner textes et tableaux.
        leftMargin=20 * mm - 6, rightMargin=20 * mm - 6, topMargin=18 * mm, bottomMargin=22 * mm,
    )
    document.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)
    return buffer.getvalue()
