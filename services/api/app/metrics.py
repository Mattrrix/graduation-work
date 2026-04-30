import asyncio
import logging

from prometheus_client import Gauge

from . import db

logger = logging.getLogger(__name__)

KNOWN_STATUSES = (
    "uploaded",
    "extracted",
    "classified",
    "validated",
    "validated_with_errors",
    "loaded",
    "failed",
)

documents_in_db = Gauge(
    "api_documents_in_db",
    "Количество документов в БД по статусу (отражает реальное состояние).",
    ["status"],
)

for _s in KNOWN_STATUSES:
    documents_in_db.labels(status=_s).set(0)


async def refresh_once() -> None:
    rows = await db.pool().fetch(
        "SELECT status::text AS status, COUNT(*) AS n FROM documents GROUP BY status"
    )
    seen: set[str] = set()
    for row in rows:
        documents_in_db.labels(status=row["status"]).set(row["n"])
        seen.add(row["status"])
    for status in KNOWN_STATUSES:
        if status not in seen:
            documents_in_db.labels(status=status).set(0)


async def refresh_loop(interval_s: float = 5.0) -> None:
    while True:
        try:
            await refresh_once()
        except Exception:
            logger.exception("documents gauge refresh failed")
        await asyncio.sleep(interval_s)
