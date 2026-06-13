"""asyncpg connection pool + a transactional-outbox helper.

Every business write goes through `write_with_outbox` so the DB row and its
outbox row commit together (docs/07-datastore.md). A change can never be
acknowledged without its follow-up work being queued.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any

import asyncpg

from .config import get_settings

_pool: asyncpg.Pool | None = None


async def init_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            get_settings().database_url, min_size=1, max_size=10, command_timeout=30
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialised")
    return _pool


@asynccontextmanager
async def tx():
    async with pool().acquire() as conn:
        async with conn.transaction():
            yield conn


async def enqueue_outbox(
    conn: asyncpg.Connection,
    *,
    aggregate: str,
    aggregate_id: str,
    event: str,
    payload: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> None:
    """Insert an outbox row inside the caller's transaction.

    ON CONFLICT on idempotency_key makes re-submits safe (no duplicate work).
    """
    await conn.execute(
        """
        INSERT INTO outbox (aggregate, aggregate_id, event, payload, idempotency_key)
        VALUES ($1, $2, $3, $4::jsonb, $5)
        ON CONFLICT (idempotency_key) DO NOTHING
        """,
        aggregate,
        aggregate_id,
        event,
        json.dumps(payload or {}),
        idempotency_key,
    )
