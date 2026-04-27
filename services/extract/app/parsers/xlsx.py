import io

import openpyxl


def parse(content: bytes, filename: str) -> dict:
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    sheets: dict[str, list[list]] = {}
    text_parts: list[str] = []
    for ws in wb.worksheets:
        rows: list[list] = []
        for row in ws.iter_rows(values_only=True):
            rows.append([("" if v is None else v) for v in row])
        sheets[ws.title] = rows
        for row in rows:
            text_parts.append("\t".join(str(v) for v in row))
    return {
        "text": "\n".join(text_parts).strip(),
        "raw": {
            "format": "xlsx",
            "sheets": sheets,
        },
    }
