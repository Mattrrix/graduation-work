from redis.asyncio import Redis

from .config import settings

_redis: Redis | None = None


async def init_redis() -> None:
    global _redis
    _redis = Redis.from_url(settings.redis_url, decode_responses=True)
    await _redis.ping()


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.close()
        _redis = None


def redis() -> Redis:
    assert _redis is not None, "redis pool not initialised"
    return _redis
