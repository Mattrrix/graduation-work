from fastapi import APIRouter, Depends, Query

from .. import auth, db
from .documents import _row_to_dict

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("")
async def search(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, le=100),
    user: dict = Depends(auth.current_user),
) -> dict:
    sql = """
        SELECT doc_id, filename, doc_type, number, doc_date, counterparty_name,
               counterparty_inn, amount_total, status, created_at,
               ts_rank(text_search, plainto_tsquery('russian', $1)) AS rank
          FROM documents
         WHERE text_search @@ plainto_tsquery('russian', $1)
         ORDER BY rank DESC, created_at DESC
         LIMIT $2
    """
    async with db.pool().acquire() as conn:
        rows = await conn.fetch(sql, q, limit)
    return {"items": [_row_to_dict(r) for r in rows]}
