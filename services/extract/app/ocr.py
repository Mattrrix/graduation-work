import base64
import io
import logging
import time
from typing import Iterable

import httpx
from pdf2image import convert_from_bytes

from .config import settings

logger = logging.getLogger(__name__)


class OcrError(Exception):
    pass


_OCR_PROMPT = "OCR. Plain text only, in natural reading order."


def _pdf_to_jpeg_b64(content: bytes, max_pages: int, dpi: int) -> Iterable[tuple[int, str]]:
    images = convert_from_bytes(content, dpi=dpi, first_page=1, last_page=max_pages)
    for idx, img in enumerate(images, start=1):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        yield idx, base64.b64encode(buf.getvalue()).decode("ascii")


async def _ocr_one_page(client: httpx.AsyncClient, b64: str) -> str:
    payload = {
        "model": settings.ocr_model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": _OCR_PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ],
        }],
        "max_tokens": settings.ocr_max_tokens_per_page,
        "temperature": 0.0,
    }
    resp = await client.post(
        f"{settings.ocr_url.rstrip('/')}/v1/chat/completions",
        json=payload,
    )
    resp.raise_for_status()
    body = resp.json()
    try:
        return body["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError) as exc:
        raise OcrError(f"unexpected_response_shape: {exc}") from exc


async def ocr_pdf(content: bytes) -> dict:
    if not settings.ocr_enabled:
        raise OcrError("ocr_disabled")

    started = time.time()
    pages: list[str] = []
    try:
        rendered = list(_pdf_to_jpeg_b64(content, settings.ocr_max_pages, settings.ocr_dpi))
    except Exception as exc:
        raise OcrError(f"pdf_render_failed: {type(exc).__name__}: {exc}") from exc

    if not rendered:
        raise OcrError("no_pages")

    async with httpx.AsyncClient(timeout=settings.ocr_timeout) as client:
        for idx, b64 in rendered:
            page_started = time.time()
            try:
                text = await _ocr_one_page(client, b64)
            except httpx.HTTPError as exc:
                raise OcrError(f"http_error_page_{idx}: {exc}") from exc
            logger.info("ocr page=%d chars=%d in %.1fs", idx, len(text), time.time() - page_started)
            pages.append(text.strip())

    full = "\n\n".join(p for p in pages if p).strip()
    return {
        "text": full,
        "pages": len(pages),
        "elapsed_s": round(time.time() - started, 2),
    }
