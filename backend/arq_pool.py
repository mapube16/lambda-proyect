"""Shared ARQ Redis connection helpers for API and Worker."""
import os
from urllib.parse import urlparse

from arq import create_pool
from arq.connections import RedisSettings, ArqRedis


def redis_url() -> str:
    # Prefer Railway private URL to avoid egress fees; fall back to public, then localhost.
    return (
        os.getenv("REDIS_PRIVATE_URL")
        or os.getenv("REDIS_URL")
        or "redis://localhost:6379"
    )


def redis_settings_from_url(url: str | None = None) -> RedisSettings:
    """Parse a redis:// URL into arq RedisSettings.

    RedisSettings does NOT accept a raw URL string (RESEARCH Pattern 2).
    Railway REDIS_URL format: redis://:password@host:port — urlparse handles
    the empty-username leading-colon correctly (Pitfall 1).
    """
    p = urlparse(url or redis_url())
    return RedisSettings(
        host=p.hostname or "localhost",
        port=p.port or 6379,
        password=p.password,
        database=int((p.path or "/").lstrip("/") or 0),
    )


async def create_arq_pool() -> ArqRedis:
    return await create_pool(redis_settings_from_url())
