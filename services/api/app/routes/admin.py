import logging
import random
import shutil
from pathlib import Path

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException

from generator import (
    DOC_TYPES,
    EDGE_CASES,
    FORMATS,
    IP_MODE_DEFAULT,
    IP_MODES,
    MISSING_MODE_DEFAULT,
    MISSING_MODES,
    PARTIES_HARD_CAP,
)
from generator.cli import generate_one
from generator.docs import MAX_PARTIES, ROLES_BY_TYPE, SUPPORTED_FORMATS
from generator.junk import write_junk

from .. import auth
from ..config import settings
from .documents import wait_for_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])

GENERATED_DIR = Path("/data/files/generated")


@router.get("/catalog")
async def catalog(user: dict = Depends(auth.current_user)) -> dict:
    return {
        "doc_types": list(DOC_TYPES),
        "formats": list(FORMATS),
        "supported_formats": {k: list(v) for k, v in SUPPORTED_FORMATS.items()},
        "edge_cases": list(EDGE_CASES),
        "ip_modes": list(IP_MODES),
        "ip_mode_default": IP_MODE_DEFAULT,
        "missing_modes": list(MISSING_MODES),
        "missing_mode_default": MISSING_MODE_DEFAULT,
        "parties_hard_cap": PARTIES_HARD_CAP,
        "max_parties_by_type": dict(MAX_PARTIES),
        "roles_by_type": {
            doc_type: [
                {"role_id": role_id, "role_label": role_label}
                for role_id, role_label in roles
            ]
            for doc_type, roles in ROLES_BY_TYPE.items()
        },
    }


@router.get("/generated")
async def list_generated(user: dict = Depends(auth.current_user)) -> dict:
    if not GENERATED_DIR.exists():
        return {"files": [], "count": 0}
    files = sorted(p for p in GENERATED_DIR.rglob("*") if p.is_file())
    return {
        "files": [
            {
                "path": str(p),
                "name": p.relative_to(GENERATED_DIR).as_posix(),
                "size": p.stat().st_size,
            }
            for p in files
        ],
        "count": len(files),
    }


@router.delete("/generated", status_code=200)
async def clear_generated(user: dict = Depends(auth.current_user)) -> dict:
    if GENERATED_DIR.exists():
        shutil.rmtree(GENERATED_DIR)
    return {"cleared": True}


@router.post("/generate")
async def generate(payload: dict = Body(...), user: dict = Depends(auth.current_user)) -> dict:
    types = payload.get("types") or ["invoice", "act", "contract"]
    formats = payload.get("formats") or list(FORMATS)
    count = max(1, min(int(payload.get("count", 5)), 200))
    junk = max(0, min(int(payload.get("junk", 0)), 200))
    seed = payload.get("seed")
    parties = max(2, min(int(payload.get("parties", 2)), PARTIES_HARD_CAP))
    edge_cases_input = payload.get("edge_cases") or []
    if not isinstance(edge_cases_input, list):
        raise HTTPException(400, "edge_cases must be a list")
    edge_cases = set(edge_cases_input)
    ip_mode = payload.get("ip_mode") or IP_MODE_DEFAULT
    if ip_mode not in IP_MODES:
        raise HTTPException(400, f"unknown ip_mode={ip_mode!r}; allowed: {list(IP_MODES)}")
    missing_mode = payload.get("missing_mode") or MISSING_MODE_DEFAULT
    if missing_mode not in MISSING_MODES:
        raise HTTPException(400, f"unknown missing_mode={missing_mode!r}; allowed: {list(MISSING_MODES)}")

    bad_types = [t for t in types if t not in DOC_TYPES]
    bad_fmts = [f for f in formats if f not in FORMATS]
    bad_edges = [e for e in edge_cases if e not in EDGE_CASES]
    if bad_types or bad_fmts or bad_edges:
        raise HTTPException(
            400, f"unknown types={bad_types} formats={bad_fmts} edge_cases={bad_edges}"
        )

    rng = random.Random(seed)
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    for doc_type in types:
        for fmt in formats:
            if fmt not in SUPPORTED_FORMATS[doc_type]:
                continue
            for i in range(1, count + 1):
                path = generate_one(
                    doc_type, fmt, GENERATED_DIR / doc_type, i, rng,
                    parties=parties, edge_cases=edge_cases,
                    ip_mode=ip_mode, missing_mode=missing_mode,
                )
                if path is not None:
                    written.append(str(path))

    if junk:
        junk_paths = write_junk(GENERATED_DIR / "junk", junk, rng)
        written.extend(str(p) for p in junk_paths)

    logger.info(
        "generated %d files into %s (parties=%d, edge_cases=%s, ip_mode=%s, missing_mode=%s)",
        len(written), GENERATED_DIR, parties, sorted(edge_cases), ip_mode, missing_mode,
    )
    return {
        "count": len(written),
        "out_dir": str(GENERATED_DIR),
        "files": written,
        "parties": parties,
        "edge_cases": sorted(edge_cases),
        "ip_mode": ip_mode,
        "missing_mode": missing_mode,
    }


@router.post("/upload-generated")
async def upload_generated(payload: dict = Body(default={}), user: dict = Depends(auth.current_user)) -> dict:
    if not GENERATED_DIR.exists():
        raise HTTPException(404, "no generated files; call /api/admin/generate first")

    paths_input = payload.get("paths")
    if paths_input:
        paths = [Path(p) for p in paths_input]
    else:
        paths = sorted(p for p in GENERATED_DIR.rglob("*") if p.is_file())

    cleanup = bool(payload.get("cleanup", False))

    results: list[dict] = []
    ok = 0
    new_count = 0
    dup_count = 0
    async with httpx.AsyncClient(base_url=settings.extract_url, timeout=120.0) as client:
        for path in paths:
            try:
                content = path.read_bytes()
                files = {"file": (path.name, content, "application/octet-stream")}
                resp = await client.post("/api/documents", files=files)
                ok_flag = resp.status_code < 400
                body = resp.json() if ok_flag else {}
                deduplicated = bool(body.get("deduplicated"))
                if ok_flag:
                    ok += 1
                    if deduplicated:
                        dup_count += 1
                    else:
                        new_count += 1
                results.append({
                    "name": path.relative_to(GENERATED_DIR).as_posix(),
                    "http_status": resp.status_code,
                    "doc_id": body.get("doc_id") if ok_flag else None,
                    "deduplicated": deduplicated,
                    "original_status": body.get("original_status") if deduplicated else None,
                    "error": None if ok_flag else resp.text[:300],
                })
            except Exception as exc:
                results.append({
                    "name": path.name,
                    "http_status": 0,
                    "doc_id": None,
                    "deduplicated": False,
                    "error": f"{type(exc).__name__}: {exc}",
                })

    doc_ids = [r["doc_id"] for r in results if r.get("doc_id") and not r.get("deduplicated")]
    final = await wait_for_pipeline(doc_ids)
    for r in results:
        r["final_status"] = final.get(r["doc_id"]) if r.get("doc_id") else None

    loaded = sum(1 for r in results if r.get("final_status") == "loaded")
    warnings = sum(1 for r in results if r.get("final_status") == "validated_with_errors")
    pipeline_failed = sum(1 for r in results if r.get("final_status") == "failed")
    rejected = len(results) - ok
    failed_total = pipeline_failed + rejected

    if cleanup:
        shutil.rmtree(GENERATED_DIR, ignore_errors=True)

    return {
        "total": len(results),
        "ok": ok,
        "new": new_count,
        "loaded": loaded,
        "warnings": warnings,
        "duplicates": dup_count,
        "failed": failed_total,
        "rejected": rejected,
        "pipeline_failed": pipeline_failed,
        "results": results,
        "cleaned": cleanup,
    }
