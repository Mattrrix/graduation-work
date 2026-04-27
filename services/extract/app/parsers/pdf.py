import io

import pdfplumber


def parse(content: bytes, filename: str) -> dict:
    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            pages.append(text)
    text = "\n".join(pages).strip()
    return {
        "text": text,
        "raw": {
            "format": "pdf",
            "page_count": len(pages),
            "needs_ocr": len(text) == 0,
        },
    }
