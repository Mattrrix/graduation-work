import asyncpg

from .config import settings

_pool: asyncpg.Pool | None = None


def _asyncpg_dsn(dsn: str) -> str:
    return dsn.replace("postgresql+asyncpg://", "postgresql://")


async def init_pool() -> None:
    global _pool
    _pool = await asyncpg.create_pool(_asyncpg_dsn(settings.postgres_dsn), min_size=1, max_size=8)


async def close_pool() -> None:
    if _pool is not None:
        await _pool.close()


def pool() -> asyncpg.Pool:
    assert _pool is not None, "DB pool is not initialised"
    return _pool
