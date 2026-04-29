import asyncio
import datetime
import json
import re
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import UUID

import httpx
from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from .. import auth, db
from ..config import settings

router = APIRouter(prefix="/api/documents", tags=["documents"])

TERMINAL_STATUSES = {"loaded", "validated_with_errors", "failed"}


async def wait_for_pipeline(doc_ids: list[str], timeout: float = 30.0) -> dict[str, str]:
    if not doc_ids:
        return {}
    deadline = time.monotonic() + timeout
    statuses: dict[str, str] = {}
    async with db.pool().acquire() as conn:
        while time.monotonic() < deadline:
            rows = await conn.fetch(
                "SELECT doc_id::text AS id, status::text AS status FROM documents WHERE doc_id = ANY($1::uuid[])",
                doc_ids,
            )
            statuses = {r["id"]: r["status"] for r in rows}
            if len(statuses) == len(doc_ids) and all(s in TERMINAL_STATUSES for s in statuses.values()):
                return statuses
            await asyncio.sleep(0.3)
    return statuses


def _row_to_dict(row) -> dict:
    d = dict(row)
    for k, v in list(d.items()):
        if isinstance(v, UUID):
            d[k] = str(v)
        if k in ("raw", "fields", "payload") and isinstance(v, str):
            d[k] = json.loads(v)
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
    return d


@router.post("", status_code=202)
async def upload(file: UploadFile = File(...), user: dict = Depends(auth.current_user)) -> dict:
    async with httpx.AsyncClient(base_url=settings.extract_url, timeout=60) as client:
        files = {"file": (file.filename, await file.read(), file.content_type or "application/octet-stream")}
        resp = await client.post("/api/documents", files=files)
    if resp.status_code >= 400:
        raise HTTPException(resp.status_code, resp.text)
    return resp.json()


@router.post("/{doc_id}/reprocess", status_code=202)
async def reprocess(doc_id: UUID, user: dict = Depends(auth.current_user)) -> dict:
    async with httpx.AsyncClient(base_url=settings.extract_url, timeout=30) as client:
        resp = await client.post(f"/api/documents/{doc_id}/reprocess")
    if resp.status_code >= 400:
        raise HTTPException(resp.status_code, resp.text)
    return resp.json()


SORTABLE_COLUMNS = {
    "filename", "doc_type", "number", "doc_date",
    "counterparty_name", "counterparty_inn", "amount_total",
    "status", "created_at",
}


@router.get("")
async def list_documents(
    status: str | None = Query(None),
    doc_type: str | None = Query(None),
    inn: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    user: dict = Depends(auth.current_user),
) -> dict:
    where: list[str] = []
    args: list = []
    if status:
        args.append(status); where.append(f"d.status = ${len(args)}::doc_status")
    if doc_type:
        args.append(doc_type); where.append(f"d.doc_type = ${len(args)}")
    if inn:
        args.append(inn); where.append(f"d.counterparty_inn = ${len(args)}")
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    if sort_by not in SORTABLE_COLUMNS:
        sort_by = "created_at"
    direction = "ASC" if sort_order.lower() == "asc" else "DESC"
    nulls = "NULLS FIRST" if direction == "ASC" else "NULLS LAST"

    args.extend([limit, offset])
    sql = f"""
        SELECT d.doc_id, d.filename, d.mime_type, d.size_bytes, d.status, d.doc_type,
               d.number, d.doc_date, d.counterparty_name, d.counterparty_inn, d.amount_total,
               d.currency, d.created_at, d.updated_at,
               (SELECT e.stage FROM processing_events e
                 WHERE e.doc_id = d.doc_id
                 ORDER BY e.created_at DESC, e.id DESC LIMIT 1) AS last_stage
          FROM documents d
          {where_sql}
         ORDER BY d.{sort_by} {direction} {nulls}, d.doc_id
         LIMIT ${len(args) - 1} OFFSET ${len(args)}
    """
    async with db.pool().acquire() as conn:
        rows = await conn.fetch(sql, *args)
        total = await conn.fetchval(f"SELECT COUNT(*) FROM documents d{where_sql}", *args[:-2])
    return {"items": [_row_to_dict(r) for r in rows], "total": int(total)}


@router.post("/wait-final")
async def wait_final(payload: dict = Body(...), user: dict = Depends(auth.current_user)) -> dict:
    raw_ids = payload.get("doc_ids") or []
    timeout = float(payload.get("timeout", 30.0))
    doc_ids = [str(UUID(x)) for x in raw_ids]
    statuses = await wait_for_pipeline(doc_ids, timeout=min(timeout, 60.0))
    return {"statuses": statuses}


@router.post("/statuses")
async def get_statuses(payload: dict = Body(...), user: dict = Depends(auth.current_user)) -> dict:
    raw_ids = payload.get("doc_ids") or []
    if not raw_ids:
        return {"items": {}}
    doc_ids = [UUID(x) for x in raw_ids]
    async with db.pool().acquire() as conn:
        status_rows = await conn.fetch(
            "SELECT doc_id::text AS id, status::text AS status FROM documents WHERE doc_id = ANY($1::uuid[])",
            doc_ids,
        )
        last_event_rows = await conn.fetch(
            """
            SELECT DISTINCT ON (doc_id) doc_id::text AS id, stage, status::text AS evstatus, message
              FROM processing_events
             WHERE doc_id = ANY($1::uuid[])
             ORDER BY doc_id, created_at DESC, id DESC
            """,
            doc_ids,
        )
        stage_rows = await conn.fetch(
            """
            SELECT doc_id::text AS id, ARRAY_AGG(DISTINCT stage::text) AS stages
              FROM processing_events
             WHERE doc_id = ANY($1::uuid[])
             GROUP BY doc_id
            """,
            doc_ids,
        )
    items: dict[str, dict] = {}
    for r in status_rows:
        items[r["id"]] = {"status": r["status"], "stages": [], "last": None}
    for r in stage_rows:
        if r["id"] in items:
            items[r["id"]]["stages"] = list(r["stages"] or [])
    for r in last_event_rows:
        if r["id"] in items:
            items[r["id"]]["last"] = {
                "stage": r["stage"],
                "status": r["evstatus"],
                "message": r["message"] or "",
            }
    return {"items": items}


@router.get("/stats")
async def stats(user: dict = Depends(auth.current_user)) -> dict:
    async with db.pool().acquire() as conn:
        rows = await conn.fetch("SELECT status::text AS status, COUNT(*)::int AS n FROM documents GROUP BY status")
        total = await conn.fetchval("SELECT COUNT(*) FROM documents")
    return {"total": int(total), "by_status": {r["status"]: r["n"] for r in rows}}


@router.get("/{doc_id}")
async def get_document(doc_id: UUID, user: dict = Depends(auth.current_user)) -> dict:
    async with db.pool().acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM documents WHERE doc_id = $1", doc_id)
    if row is None:
        raise HTTPException(404, "not found")
    return _row_to_dict(row)


EDITABLE_FIELDS = {
    "doc_type": "text",
    "number": "text",
    "doc_date": "date",
    "counterparty_name": "text",
    "counterparty_inn": "inn",
    "counterparty_kpp": "kpp",
    "amount_total": "numeric",
    "vat_rate": "vat_rate",
}

CP_TEXT_KEYS = ("name", "inn", "kpp", "form", "role")

INN_RE = re.compile(r"^\d{10}$|^\d{12}$")
KPP_RE = re.compile(r"^\d{4}[\dA-Z]{2}\d{3}$")  # 4 цифры + 2 цифры/латинских заглавных + 3 цифры


def _validate_inn(value: str, *, field: str) -> str:
    if not INN_RE.match(value):
        raise HTTPException(400, f"{field}: ИНН должен содержать ровно 10 или 12 цифр")
    return value


def _validate_kpp(value: str, *, field: str) -> str:
    if not KPP_RE.match(value.upper()):
        raise HTTPException(400, f"{field}: КПП должен быть из 9 символов (например, 770101001)")
    return value.upper()


def _validate_vat_rate(value: str, *, field: str) -> Decimal:
    try:
        n = Decimal(value.replace(",", ".").replace(" ", ""))
    except (InvalidOperation, ValueError):
        raise HTTPException(400, f"{field}: ставка НДС должна быть числом")
    if n < 0 or n > 100:
        raise HTTPException(400, f"{field}: ставка НДС должна быть от 0 до 100")
    return n


def _normalize_counterparties(raw) -> list[dict]:
    if not isinstance(raw, list):
        raise HTTPException(400, "counterparties must be a list")
    cleaned: list[dict] = []
    for i, cp in enumerate(raw):
        if not isinstance(cp, dict):
            raise HTTPException(400, f"counterparty[{i}] must be an object")
        item: dict = {}
        for key in CP_TEXT_KEYS:
            v = cp.get(key)
            item[key] = str(v).strip() if v not in (None, "") else None
        if item["inn"]:
            _validate_inn(item["inn"], field=f"Контрагент №{i + 1} / ИНН")
        if item["kpp"]:
            item["kpp"] = _validate_kpp(item["kpp"], field=f"Контрагент №{i + 1} / КПП")
        item["is_primary"] = bool(cp.get("is_primary"))
        if item["name"] or item["inn"]:
            cleaned.append(item)
    primaries = [i for i, c in enumerate(cleaned) if c["is_primary"]]
    if cleaned and not primaries:
        cleaned[0]["is_primary"] = True
    elif len(primaries) > 1:
        for i in primaries[1:]:
            cleaned[i]["is_primary"] = False
    return cleaned


def _granular_cp_diffs(old: list, new: list) -> dict:
    out: dict = {}
    n = max(len(old), len(new))
    for i in range(n):
        old_cp = old[i] if i < len(old) else None
        new_cp = new[i] if i < len(new) else None
        idx = i + 1
        cp_name = (
            (old_cp or {}).get("name")
            or (new_cp or {}).get("name")
            or None
        )
        if old_cp is None and new_cp is not None:
            out[f"counterparty_{idx}_added"] = {
                "old": None,
                "new": new_cp.get("name") or "(без имени)",
                "cp_name": cp_name,
                "cp_idx": idx,
            }
            continue
        if new_cp is None and old_cp is not None:
            out[f"counterparty_{idx}_removed"] = {
                "old": old_cp.get("name") or "(без имени)",
                "new": None,
                "cp_name": cp_name,
                "cp_idx": idx,
            }
            continue
        is_primary = bool((new_cp or {}).get("is_primary")) or bool((old_cp or {}).get("is_primary"))
        skip = {"name", "inn", "kpp"} if is_primary else set()
        for fld in ("name", "inn", "kpp", "form", "role"):
            if fld in skip:
                continue
            old_v = (old_cp or {}).get(fld) or None
            new_v = (new_cp or {}).get(fld) or None
            if old_v != new_v:
                out[f"counterparty_{idx}_{fld}"] = {
                    "old": old_v,
                    "new": new_v,
                    "cp_name": cp_name,
                    "cp_idx": idx,
                }
        if bool((old_cp or {}).get("is_primary")) != bool((new_cp or {}).get("is_primary")):
            out[f"counterparty_{idx}_primary"] = {
                "old": "да" if (old_cp or {}).get("is_primary") else "нет",
                "new": "да" if (new_cp or {}).get("is_primary") else "нет",
                "cp_name": cp_name,
                "cp_idx": idx,
            }
    return out


@router.patch("/{doc_id}")
async def patch_document(
    doc_id: UUID,
    payload: dict = Body(...),
    user: dict = Depends(auth.current_user),
) -> dict:
    overrides = payload.get("fields") or {}
    if not isinstance(overrides, dict) or not overrides:
        raise HTTPException(400, "fields object is required")

    cp_override = None
    if "counterparties" in overrides:
        cp_override = _normalize_counterparties(overrides.pop("counterparties"))

    unknown = [k for k in overrides if k not in EDITABLE_FIELDS]
    if unknown:
        raise HTTPException(400, f"unknown fields: {unknown}")

    if cp_override is not None:
        primary = next((c for c in cp_override if c["is_primary"]), None)
        overrides["counterparty_name"] = primary["name"] if primary else None
        overrides["counterparty_inn"] = primary["inn"] if primary else None
        overrides["counterparty_kpp"] = primary["kpp"] if primary else None

    set_clauses: list[str] = []
    args: list = [doc_id]
    for key, val in overrides.items():
        kind = EDITABLE_FIELDS[key]
        coerced: object | None
        if val is None or (isinstance(val, str) and not val.strip()):
            coerced = None
        else:
            raw = str(val).strip()
            if kind == "date":
                try:
                    coerced = datetime.date.fromisoformat(raw)
                except ValueError:
                    raise HTTPException(400, f"Дата {key}: ожидается формат YYYY-MM-DD")
                if coerced.year < 1900 or coerced.year > 2100:
                    raise HTTPException(400, f"Дата {key}: год вне диапазона 1900–2100")
            elif kind == "numeric":
                try:
                    coerced = Decimal(raw.replace(",", ".").replace(" ", ""))
                except (InvalidOperation, ValueError):
                    raise HTTPException(400, f"{key}: значение должно быть числом")
            elif kind == "vat_rate":
                coerced = _validate_vat_rate(raw, field="Ставка НДС")
            elif kind == "inn":
                coerced = _validate_inn(raw, field="ИНН")
            elif kind == "kpp":
                coerced = _validate_kpp(raw, field="КПП")
            else:
                coerced = raw
        args.append(coerced)
        idx = len(args)
        set_clauses.append(f"{key} = ${idx}")

    async with db.pool().acquire() as conn:
        before = await conn.fetchrow(
            f"SELECT {', '.join(EDITABLE_FIELDS)}, fields FROM documents WHERE doc_id = $1",
            doc_id,
        )
        if before is None:
            raise HTTPException(404, "not found")

        if set_clauses:
            await conn.execute(
                f"UPDATE documents SET {', '.join(set_clauses)}, updated_at = NOW() WHERE doc_id = $1",
                *args,
            )

        old_fields_raw = before["fields"]
        old_fields = json.loads(old_fields_raw) if isinstance(old_fields_raw, str) else (old_fields_raw or {})
        old_cps = old_fields.get("counterparties") or []
        old_primary_idx = next(
            (i + 1 for i, c in enumerate(old_cps) if c.get("is_primary")),
            None,
        )
        old_primary_name = next((c.get("name") for c in old_cps if c.get("is_primary")), None)
        primary_label = (
            (overrides.get("counterparty_name") if "counterparty_name" in overrides else None)
            or old_primary_name
        )

        cp_label_for_flat = old_primary_name or primary_label

        diffs = {}
        for k, new_v in overrides.items():
            old_v = before[k]
            old_str = str(old_v) if old_v is not None else None
            new_str = (str(new_v).strip() or None) if new_v not in (None, "") else None
            if old_str != new_str:
                entry: dict = {"old": old_str, "new": new_str}
                if k in ("counterparty_name", "counterparty_inn", "counterparty_kpp"):
                    if cp_label_for_flat:
                        entry["cp_name"] = cp_label_for_flat
                    if old_primary_idx:
                        entry["cp_idx"] = old_primary_idx
                diffs[k] = entry

        if cp_override is not None:
            new_fields = {**old_fields, "counterparties": cp_override}
            await conn.execute(
                "UPDATE documents SET fields = $1::jsonb, updated_at = NOW() WHERE doc_id = $2",
                json.dumps(new_fields, ensure_ascii=False, default=str),
                doc_id,
            )
            diffs.update(_granular_cp_diffs(old_cps, cp_override))

        if diffs:
            await conn.execute(
                """
                INSERT INTO processing_events(doc_id, stage, status, message, payload)
                VALUES ($1, 'override', 'ok', $2, $3::jsonb)
                """,
                doc_id,
                f"manual_override by {user.get('sub') or user.get('username') or '?'}: {', '.join(diffs)}",
                json.dumps({"by": user.get("sub") or user.get("username"), "diffs": diffs}, ensure_ascii=False),
            )

        row = await conn.fetchrow("SELECT * FROM documents WHERE doc_id = $1", doc_id)

    return _row_to_dict(row)


@router.get("/{doc_id}/audit")
async def get_audit(doc_id: UUID, user: dict = Depends(auth.current_user)) -> list[dict]:
    async with db.pool().acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, stage, status, message, payload, created_at FROM processing_events WHERE doc_id = $1 ORDER BY created_at, id",
            doc_id,
        )
    return [_row_to_dict(r) for r in rows]


SUMMARY_PROMPT = """Это полный текст русскоязычного бизнес-документа. \
Напиши развёрнутое резюме на 3-6 предложений на русском языке.
Опиши: что это за документ, кто стороны, что является предметом, ключевые суммы и даты, особенности.
Без вводных слов, без префикса "Резюме:", сразу содержательно.

Документ:
\"\"\"
{text}
\"\"\""""


@router.post("/{doc_id}/summary")
async def summarize(doc_id: UUID, user: dict = Depends(auth.current_user)) -> StreamingResponse:
    async with db.pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT text_content FROM documents WHERE doc_id = $1",
            doc_id,
        )
    if row is None:
        raise HTTPException(404, "not found")
    text = (row["text_content"] or "").strip()
    if not text:
        raise HTTPException(400, "no text content to summarize")

    prompt = SUMMARY_PROMPT.format(text=text[:48000])
    payload = {
        "model": settings.qwen_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": settings.qwen_summary_max_tokens,
        "stream": True,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    url = f"{settings.qwen_url.rstrip('/')}/v1/chat/completions"

    async def gen():
        chunks: list[str] = []
        try:
            async with httpx.AsyncClient(timeout=settings.qwen_summary_timeout) as client:
                async with client.stream("POST", url, json=payload) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            j = json.loads(data)
                            delta = j["choices"][0].get("delta", {})
                            piece = delta.get("content") or ""
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
                        if piece:
                            chunks.append(piece)
                            yield piece
        except httpx.HTTPError as e:
            yield f"\n\n[ошибка LLM: {str(e)[:120]}]"
            return

        full_text = "".join(chunks).strip()
        if full_text:
            try:
                async with db.pool().acquire() as conn:
                    await conn.execute(
                        "UPDATE documents SET summary_detailed = $1, updated_at = NOW() WHERE doc_id = $2",
                        full_text,
                        doc_id,
                    )
            except Exception:
                pass

    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")


async def _drop_blob_if_orphan(conn, sha256: str, storage_path: str) -> None:
    siblings = await conn.fetchval("SELECT COUNT(*) FROM documents WHERE sha256 = $1", sha256)
    if siblings == 0:
        path = Path(storage_path)
        if path.exists():
            path.unlink()


@router.delete("/{doc_id}", status_code=204)
async def delete_document(doc_id: UUID, user: dict = Depends(auth.current_user)) -> None:
    async with db.pool().acquire() as conn:
        row = await conn.fetchrow("SELECT storage_path, sha256 FROM documents WHERE doc_id = $1", doc_id)
        if row is None:
            raise HTTPException(404, "not found")
        await conn.execute("DELETE FROM documents WHERE doc_id = $1", doc_id)
        await _drop_blob_if_orphan(conn, row["sha256"], row["storage_path"])


@router.post("/bulk-delete", status_code=200)
async def bulk_delete(
    payload: dict = Body(..., examples=[{"doc_ids": ["..."]}, {"all": True}, {"status": "failed"}]),
    user: dict = Depends(auth.current_user),
) -> dict:
    where: list[str] = []
    args: list = []
    if payload.get("all") is True:
        where.append("TRUE")
    elif "doc_ids" in payload:
        ids = [UUID(x) for x in payload["doc_ids"]]
        if not ids:
            return {"deleted": 0}
        args.append(ids)
        where.append(f"doc_id = ANY(${len(args)})")
    elif "status" in payload:
        args.append(payload["status"])
        where.append(f"status = ${len(args)}::doc_status")
    else:
        raise HTTPException(400, "specify one of: all=true, doc_ids=[...], status=...")

    async with db.pool().acquire() as conn:
        rows = await conn.fetch(
            f"DELETE FROM documents WHERE {' AND '.join(where)} RETURNING storage_path, sha256",
            *args,
        )
        for row in rows:
            await _drop_blob_if_orphan(conn, row["sha256"], row["storage_path"])
    return {"deleted": len(rows)}


@router.get("/{doc_id}/file")
async def download(doc_id: UUID, user: dict = Depends(auth.current_user)):
    async with db.pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT filename, mime_type, storage_path FROM documents WHERE doc_id = $1",
            doc_id,
        )
    if row is None:
        raise HTTPException(404, "not found")
    path = Path(row["storage_path"])
    if not path.exists():
        raise HTTPException(410, "file is gone")
    return FileResponse(path, filename=row["filename"], media_type=row["mime_type"] or "application/octet-stream")
