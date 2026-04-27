import json
import logging
from uuid import UUID

import asyncpg

from .stages import classify, dedup, ner, normalize, validate

logger = logging.getLogger(__name__)


async def process(conn: asyncpg.Connection, message: dict) -> dict:
    doc_id = UUID(message["doc_id"])
    text = message.get("text") or ""
    filename = message.get("filename")
    sha256 = message.get("sha256") or ""

    doc_type = classify.classify(text, filename)
    extracted = ner.extract(text)
    normalized = normalize.normalize(extracted)
    errors = validate.validate(normalized)

    has_business_field = any(k in normalized for k in ("inn", "number", "amount_total"))
    if not doc_type or not has_business_field:
        doc_type = None
        errors.append({"field": "document", "code": "unknown_document_type", "value": None})

    duplicate_of = await dedup.find_exact_duplicate(conn, sha256, doc_id) if sha256 else None

    if errors:
        status = "validated_with_errors"
    else:
        status = "loaded"

    fields_payload = {
        **normalized,
        "errors": errors,
        "duplicate_of": duplicate_of,
    }

    await conn.execute(
        """
        UPDATE documents
           SET status            = $2::doc_status,
               doc_type          = $3,
               number            = $4,
               doc_date          = NULLIF($5, '')::date,
               counterparty_name = $6,
               counterparty_inn  = $7,
               counterparty_kpp  = $8,
               amount_total      = NULLIF($9, '')::numeric,
               fields            = $10::jsonb,
               updated_at        = NOW()
         WHERE doc_id = $1
        """,
        doc_id,
        status,
        doc_type,
        normalized.get("number"),
        normalized.get("date") or "",
        normalized.get("counterparty_name"),
        normalized.get("inn"),
        normalized.get("kpp"),
        normalized.get("amount_total") or "",
        json.dumps(fields_payload, ensure_ascii=False, default=str),
    )

    await conn.execute(
        """
        INSERT INTO processing_events(doc_id, stage, status, message, payload)
        VALUES ($1, 'transform', $2, $3, $4::jsonb)
        """,
        doc_id,
        "ok" if not errors else "warning",
        f"doc_type={doc_type}, errors={len(errors)}, dup={duplicate_of}",
        json.dumps({"errors": errors, "duplicate_of": duplicate_of}, ensure_ascii=False),
    )

    logger.info("processed doc_id=%s type=%s errors=%d dup=%s", doc_id, doc_type, len(errors), duplicate_of)
    return {"doc_type": doc_type or "unknown", "status": status}
