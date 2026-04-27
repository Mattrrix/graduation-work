from pathlib import Path
from typing import Callable

from . import csv as csv_parser
from . import docx as docx_parser
from . import pdf as pdf_parser
from . import txt as txt_parser
from . import xlsx as xlsx_parser

ParseFn = Callable[[bytes, str], dict]

SUPPORTED: dict[str, ParseFn] = {
    "application/pdf": pdf_parser.parse,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": docx_parser.parse,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": xlsx_parser.parse,
    "text/csv": csv_parser.parse,
    "text/plain": txt_parser.parse,
}

EXTENSION_FALLBACK: dict[str, ParseFn] = {
    ".pdf": pdf_parser.parse,
    ".docx": docx_parser.parse,
    ".xlsx": xlsx_parser.parse,
    ".csv": csv_parser.parse,
    ".txt": txt_parser.parse,
}


def resolve(mime: str | None, filename: str) -> ParseFn | None:
    if mime and mime in SUPPORTED:
        return SUPPORTED[mime]
    return EXTENSION_FALLBACK.get(Path(filename).suffix.lower())
