import json
import logging
import uuid

import magic
from fastapi import APIRouter, File, HTTPException, UploadFile
from prometheus_client import Counter, Histogram

from . import db, kafka_producer, parsers, storage

logger = logging.getLogger(__name__)

router = APIRouter()

uploads_total = Counter(
    "extract_uploads_total",
    "Total uploaded documents",
    ["mime", "result"],
)
parse_seconds = Histogram("extract_parse_seconds", "Parse latency in seconds")

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
