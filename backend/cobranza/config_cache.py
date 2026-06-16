"""
config_cache.py — Phase 25: Redis-backed tenant config cache.

Provides a 5-minute TTL read-through cache on top of MongoDB tenant_configs.
Immediate invalidation is supported so that toggle_module() changes are
reflected on the very next get_tenant_config() call (CACHE-01 contract).

Redis client:
  - Prefers UPSTASH_REDIS_URL (Upstash managed Redis — must be rediss:// with SSL).
  - Falls back to REDIS_URL (Railway) then redis://localhost:6379 (dev).

Pitfall 5 (RESEARCH): Upstash requires SSL — the URL scheme is rediss:// (not
redis://). Railway uses plain redis://. The client is configured with
ssl=True when the scheme is rediss://, ssl=False otherwise. decode_responses=True
ensures all keys/values are str, not bytes.

The module-level `_redis_client` sentinel is None by default. get_redis() lazily
creates it on first call. Tests can monkeypatch `_redis_client` to a fakeredis
instance to avoid needing a real Redis server in CI.
"""
import json
import os
from typing import Optional

import redis.asyncio as aioredis  # must be redis.asyncio (not aioredis package)

_redis_client: Optional[aioredis.Redis] = None

_CACHE_KEY_PREFIX = "tenant_config"
_TTL_SECONDS = 300  # 5-minute TTL (CACHE-01)


def _build_key(user_id: str) -> str:
    return f"{_CACHE_KEY_PREFIX}:{user_id}"


async def get_redis() -> aioredis.Redis:
    """
    Return (or lazily create) the module-level Redis client.
    Memoised — only one client is created per process lifetime.

    URL priority: UPSTASH_REDIS_URL > REDIS_URL > redis://localhost:6379
    Pitfall 5: Upstash URLs use rediss:// (SSL required); Railway uses redis://.
    """
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    url = (
        os.getenv("UPSTASH_REDIS_URL")
        or os.getenv("REDIS_URL")
        or "redis://localhost:6379"
    )
    # Upstash uses rediss:// (SSL); Railway/local use redis:// (plain).
    ssl = url.startswith("rediss://")
    _redis_client = aioredis.from_url(
        url,
        encoding="utf-8",
        decode_responses=True,
        ssl=ssl,
    )
    return _redis_client


async def get_tenant_config(user_id: str) -> dict:
    """
    Return the tenant config for user_id.

    Cache-hit path: Redis key tenant_config:{user_id} exists → json.loads and return.
    Cache-miss path: fetch from MongoDB via get_tenant_config_doc, store in Redis
                     with setex(key, 300, json_value) when doc is truthy, return doc.
    Returns {} (empty dict) when no document exists in MongoDB.

    datetime values are serialised as strings via json.dumps(default=str).
    """
    redis = await get_redis()
    key = _build_key(user_id)

    # ── Cache hit ──────────────────────────────────────────────────────────────
    try:
        cached = await redis.get(key)
        if cached is not None:
            return json.loads(cached)
    except Exception:
        # Redis unavailable — fall through to MongoDB
        pass

    # ── Cache miss: load from MongoDB ─────────────────────────────────────────
    from cobranza.tenant_config import get_tenant_config_doc
    doc = await get_tenant_config_doc(user_id)

    if doc:
        # Pop _id before caching (already str from _serialize, but remove to keep payload clean)
        cacheable = {k: v for k, v in doc.items() if k != "_id"}
        try:
            await redis.setex(key, _TTL_SECONDS, json.dumps(cacheable, default=str))
        except Exception:
            pass  # Cache write failure is non-fatal

    return doc or {}


async def invalidate_tenant_config(user_id: str) -> None:
    """
    Delete the Redis key tenant_config:{user_id}.
    The next call to get_tenant_config() will reload from MongoDB.
    Called by tenant_config.py on every successful write (CACHE-01).
    """
    redis = await get_redis()
    try:
        await redis.delete(_build_key(user_id))
    except Exception:
        # Redis unavailable — next read will miss and reload from MongoDB anyway
        pass
