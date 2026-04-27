import asyncio
import json
import time
from pathlib import Path
from uuid import UUID

import httpx
from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

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
        if k in ("raw", "fields") and isinstance(v, str):
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
        args.append(status); where.append(f"status = ${len(args)}::doc_status")
    if doc_type:
        args.append(doc_type); where.append(f"doc_type = ${len(args)}")
    if inn:
        args.append(inn); where.append(f"counterparty_inn = ${len(args)}")
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    if sort_by not in SORTABLE_COLUMNS:
        sort_by = "created_at"
    direction = "ASC" if sort_order.lower() == "asc" else "DESC"
    nulls = "NULLS FIRST" if direction == "ASC" else "NULLS LAST"

    args.extend([limit, offset])
    sql = f"""
        SELECT doc_id, filename, mime_type, size_bytes, status, doc_type, number, doc_date,
               counterparty_name, counterparty_inn, amount_total, currency, created_at, updated_at
          FROM documents
          {where_sql}
         ORDER BY {sort_by} {direction} {nulls}, doc_id
         LIMIT ${len(args) - 1} OFFSET ${len(args)}
    """
    async with db.pool().acquire() as conn:
        rows = await conn.fetch(sql, *args)
        total = await conn.fetchval(f"SELECT COUNT(*) FROM documents{where_sql}", *args[:-2])
    return {"items": [_row_to_dict(r) for r in rows], "total": int(total)}


@router.post("/wait-final")
async def wait_final(payload: dict = Body(...), user: dict = Depends(auth.current_user)) -> dict:
    raw_ids = payload.get("doc_ids") or []
    timeout = float(payload.get("timeout", 30.0))
    doc_ids = [str(UUID(x)) for x in raw_ids]
    statuses = await wait_for_pipeline(doc_ids, timeout=min(timeout, 60.0))
    return {"statuses": statuses}


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


@router.get("/{doc_id}/audit")
async def get_audit(doc_id: UUID, user: dict = Depends(auth.current_user)) -> list[dict]:
    async with db.pool().acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, stage, status, message, payload, created_at FROM processing_events WHERE doc_id = $1 ORDER BY created_at",
            doc_id,
        )
    return [_row_to_dict(r) for r in rows]


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
