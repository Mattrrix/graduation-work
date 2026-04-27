from __future__ import annotations

import logging
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import _text

logger = logging.getLogger(__name__)


_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
]

_FONT_NAME: str | None = None


def _ensure_unicode_font() -> str | None:
    global _FONT_NAME
    if _FONT_NAME is not None:
        return _FONT_NAME
    for path in _FONT_CANDIDATES:
        p = Path(path)
        if p.exists():
            name = p.stem.replace(" ", "")
            try:
                pdfmetrics.registerFont(TTFont(name, str(p)))
                _FONT_NAME = name
                logger.info("PDF font: %s (%s)", name, p)
                return name
            except Exception as exc:
                logger.warning("font %s rejected: %s", p, exc)
    logger.warning(
        "no Unicode TTF found in standard locations; PDF will use Helvetica and Cyrillic glyphs will be missing"
    )
    return None


def write(d: dict, path: Path) -> None:
    font = _ensure_unicode_font() or "Helvetica"

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("Title", parent=styles["Title"], fontName=font, fontSize=16, alignment=1)
    body_style = ParagraphStyle("Body", parent=styles["BodyText"], fontName=font, fontSize=10, leading=14)

    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    story = [Paragraph(d["title"], title_style), Spacer(1, 0.3 * cm)]
    for line in _text.render_lines(d)[1:]:
        story.append(Paragraph(line.replace(" ", "&nbsp;") if line == "" else line, body_style))

    if "items" in d and d["items"]:
        rows = _text.items_table(d["items"])
        table = Table(rows, repeatRows=1)
        table.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, -1), font, 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(Spacer(1, 0.4 * cm))
        story.append(table)

    doc.build(story)
