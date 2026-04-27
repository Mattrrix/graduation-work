import asyncpg


async def find_exact_duplicate(conn: asyncpg.Connection, sha256: str, exclude_doc_id) -> str | None:
    row = await conn.fetchrow(
        "SELECT doc_id FROM documents WHERE sha256 = $1 AND doc_id <> $2 LIMIT 1",
        sha256,
        exclude_doc_id,
    )
    return str(row["doc_id"]) if row else None
