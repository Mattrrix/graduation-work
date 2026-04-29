import json
import logging
import uuid
from uuid import UUID

import magic
from fastapi import APIRouter, File, HTTPException, UploadFile
from prometheus_client import Counter, Histogram

from . import db, kafka_producer, parsers, storage
from . import ocr as ocr_client
from .config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

uploads_total = Counter(
    "extract_uploads_total",
    "Total uploaded documents",
    ["mime", "result"],
)
parse_seconds = Histogram("extract_parse_seconds", "Parse latency in seconds")
ocr_seconds = Histogram("extract_ocr_seconds", "OCR latency in seconds")
ocr_total = Counter(
    "extract_ocr_total",
    "OCR fallback invocations on scanned PDFs",
    ["result"],
)
for _r in ("ok", "failed", "disabled"):
    ocr_total.labels(result=_r)

_KNOWN_RESULTS = ("new", "deduplicated", "parse_failed", "kafka_failed")
_KNOWN_MIMES = (
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/csv",
    "text/plain",
)
for _m in _KNOWN_MIMES:
    for _r in _KNOWN_RESULTS:
        uploads_total.labels(mime=_m, result=_r)


@router.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@router.post("/api/documents", status_code=202)
async def upload_document(file: UploadFile = File(...)) -> dict:
    content = await file.read()
    if not content:
        raise HTTPException(400, "Empty file")

    mime = magic.from_buffer(content, mime=True) or file.content_type
    parser = parsers.resolve(mime, file.filename or "")
    if parser is None:
        raise HTTPException(415, f"Unsupported file type: mime={mime}, name={file.filename}")

    sha, path = storage.save_blob(content, file.filename or "blob")

    async with db.pool().acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT doc_id, status, filename FROM documents WHERE sha256 = $1",
            sha,
        )
        if existing is not None:
            uploads_total.labels(mime=mime, result="deduplicated").inc()
            return {
                "doc_id": str(existing["doc_id"]),
                "deduplicated": True,
                "original_status": existing["status"],
                "original_filename": existing["filename"],
            }

        doc_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO documents (doc_id, filename, mime_type, size_bytes, sha256, storage_path, status)
            VALUES ($1, $2, $3, $4, $5, $6, 'uploaded')
            """,
            doc_id,
            file.filename,
            mime,
            len(content),
            sha,
            path,
        )

    try:
        with parse_seconds.time():
            parsed = parser(content, file.filename or "")
        if (
            mime == "application/pdf"
            and not parsed.get("text")
            and parsed.get("raw", {}).get("needs_ocr")
        ):
            parsed = await _run_ocr(doc_id, content, parsed)
    except Exception as exc:
        logger.warning(
            "parser rejected file (HTTP 422 to client): doc_id=%s mime=%s exc=%s: %s",
            doc_id, mime, type(exc).__name__, str(exc)[:200],
        )
        async with db.pool().acquire() as conn:
            await conn.execute(
                "UPDATE documents SET status = 'failed', updated_at = NOW() WHERE doc_id = $1",
                doc_id,
            )
            await conn.execute(
                "INSERT INTO processing_events(doc_id, stage, status, message) VALUES ($1, 'extract', 'error', $2)",
                doc_id,
                f"parser_failed: {type(exc).__name__}: {exc}"[:500],
            )
        uploads_total.labels(mime=mime, result="parse_failed").inc()
        raise HTTPException(422, f"Cannot parse file: {type(exc).__name__}: {exc}")

    async with db.pool().acquire() as conn:
        await conn.execute(
            """
            UPDATE documents
               SET status = 'extracted',
                   text_content = $2,
                   raw = $3::jsonb,
                   updated_at = NOW()
             WHERE doc_id = $1
            """,
            doc_id,
            parsed["text"],
            json.dumps(parsed["raw"], ensure_ascii=False, default=str),
        )
        await conn.execute(
            "INSERT INTO processing_events(doc_id, stage, status, message) VALUES ($1, 'extract', 'ok', $2)",
            doc_id,
            f"parsed mime={mime}",
        )

    try:
        await kafka_producer.publish_raw(
            str(doc_id),
            {
                "doc_id": str(doc_id),
                "filename": file.filename,
                "mime": mime,
                "sha256": sha,
                "storage_path": path,
                "text": parsed["text"],
                "raw": parsed["raw"],
            },
        )
    except Exception as exc:
        logger.exception("kafka publish failed for doc_id=%s", doc_id)
        async with db.pool().acquire() as conn:
            await conn.execute(
                "UPDATE documents SET status = 'failed', updated_at = NOW() WHERE doc_id = $1",
                doc_id,
            )
            await conn.execute(
                "INSERT INTO processing_events(doc_id, stage, status, message) VALUES ($1, 'extract', 'error', $2)",
                doc_id,
                f"kafka_publish_failed: {type(exc).__name__}: {exc}"[:500],
            )
        uploads_total.labels(mime=mime, result="kafka_failed").inc()
        raise HTTPException(503, "Kafka publish failed")

    uploads_total.labels(mime=mime, result="new").inc()
    return {"doc_id": str(doc_id), "deduplicated": False}


async def _run_ocr(doc_id: uuid.UUID, content: bytes, parsed: dict) -> dict:
    if not settings.ocr_enabled:
        ocr_total.labels(result="disabled").inc()
        return parsed
    try:
        with ocr_seconds.time():
            result = await ocr_client.ocr_pdf(content)
    except ocr_client.OcrError as exc:
        ocr_total.labels(result="failed").inc()
        logger.warning("ocr failed: doc_id=%s exc=%s", doc_id, exc)
        async with db.pool().acquire() as conn:
            await conn.execute(
                "INSERT INTO processing_events(doc_id, stage, status, message) VALUES ($1, 'ocr', 'error', $2)",
                doc_id,
                f"ocr_failed: {exc}"[:500],
            )
        return parsed

    ocr_total.labels(result="ok").inc()
    raw = dict(parsed.get("raw") or {})
    raw["ocr"] = {
        "engine": settings.ocr_model,
        "pages": result["pages"],
        "elapsed_s": result["elapsed_s"],
    }
    raw["needs_ocr"] = False
    pages = result["pages"]
    chars = len(result["text"])
    elapsed = result["elapsed_s"]
    page_word = "страница" if pages == 1 else ("страницы" if 2 <= pages <= 4 else "страниц")
    msg = f"Распознан скан: {pages} {page_word}, извлечено {chars} символов за {elapsed:.1f} с"
    async with db.pool().acquire() as conn:
        await conn.execute(
            "INSERT INTO processing_events(doc_id, stage, status, message) VALUES ($1, 'ocr', 'ok', $2)",
            doc_id,
            msg,
        )
    return {"text": result["text"], "raw": raw}


@router.post("/api/documents/{doc_id}/reprocess", status_code=202)
async def reprocess_document(doc_id: UUID) -> dict:
    async with db.pool().acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT filename, mime_type, sha256, storage_path, text_content, raw
              FROM documents
             WHERE doc_id = $1
            """,
            doc_id,
        )
    if row is None:
        raise HTTPException(404, "not found")
    text = row["text_content"]
    if not text:
        raise HTTPException(409, "no text_content; cannot reprocess")

    raw = row["raw"]
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}

    async with db.pool().acquire() as conn:
        await conn.execute(
            "UPDATE documents SET status = 'extracted', updated_at = NOW() WHERE doc_id = $1",
            doc_id,
        )
        await conn.execute(
            "INSERT INTO processing_events(doc_id, stage, status, message) VALUES ($1, 'extract', 'ok', 'reprocess_requested')",
            doc_id,
        )

    try:
        await kafka_producer.publish_raw(
            str(doc_id),
            {
                "doc_id": str(doc_id),
                "filename": row["filename"],
                "mime": row["mime_type"],
                "sha256": row["sha256"],
                "storage_path": row["storage_path"],
                "text": text,
                "raw": raw or {},
            },
        )
    except Exception as exc:
        logger.exception("kafka republish failed for doc_id=%s", doc_id)
        raise HTTPException(503, f"Kafka publish failed: {type(exc).__name__}")

    return {"doc_id": str(doc_id), "reprocessed": True}
