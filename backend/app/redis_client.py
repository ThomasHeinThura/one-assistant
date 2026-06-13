"""Redis: shared async client + coordination primitives.

Provides the cache, idempotency keys, and per-entity distributed locks the
worker pools use (docs/07-datastore.md). The message bus lives in app/bus.py and
also rides on this connection when the backend is Redis Streams.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

import redis.asyncio as redis

from .config import get_settings

_client: redis.Redis | None = None


def client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(get_settings().redis_url, decode_responses=True)
    return _client


async def close() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def ping() -> bool:
    try:
        return bool(await client().ping())
    except Exception:
        return False


async def seen_before(key: str, ttl_seconds: int = 86_400) -> bool:
    """Idempotency guard: returns True if this key was already processed.

    Uses SET NX so the check-and-mark is atomic across worker replicas.
    """
    was_set = await client().set(f"idem:{key}", "1", nx=True, ex=ttl_seconds)
    return not bool(was_set)


@asynccontextmanager
async def entity_lock(entity: str, *, ttl_ms: int = 30_000):
    """Per-entity lock so two workers never touch the same deal/ticket at once.

    Best-effort (single-node Redis); upgrade to Redlock if Redis is clustered.
    """
    r = client()
    token = entity  # value not used for fencing here; presence is the lock
    acquired = await r.set(f"lock:{entity}", token, nx=True, px=ttl_ms)
    try:
        yield bool(acquired)
    finally:
        if acquired:
            await r.delete(f"lock:{entity}")
