"""Background worker runner (skeleton).

Drains the transactional outbox and fans work out to the dedicated steps from
docs/07-datastore.md. In M0 this is a single process polling the outbox; in
later milestones each pool (reindex / dispatch / derive / verify) gets its own
Redis queue and can scale independently.

Run with:  python -m app.workers
"""
from __future__ import annotations

import asyncio
import logging

from .config import get_settings
from .db import close_pool, init_pool, pool
from .integrations.notion import NotionAdapter
from .integrations.plane import PlaneAdapter

log = logging.getLogger("maria.workers")
POLL_SECONDS = 2
MAX_ATTEMPTS = 8


def backoff_seconds(attempts: int) -> int:
    return min(300, 2 ** attempts)  # exponential, capped at 5 min


async def claim_batch(conn, limit: int = 10):
    # SKIP LOCKED lets multiple worker replicas drain safely without double-processing.
    return await conn.fetch(
        """
        UPDATE outbox SET status='processing', attempts=attempts+1
        WHERE id IN (
          SELECT id FROM outbox
          WHERE status IN ('pending','failed') AND available_at <= now()
          ORDER BY available_at
          FOR UPDATE SKIP LOCKED
          LIMIT $1
        )
        RETURNING *
        """,
        limit,
    )


async def handle(row, settings) -> None:
    """Route one outbox event. Each branch is idempotent.

    Real reindex/dispatch/derive/verify bodies land in M2–M4; here we mark done
    so the pipeline is exercisable end to end.
    """
    event = row["event"]
    log.info("processing outbox id=%s %s/%s event=%s", row["id"], row["aggregate"], row["aggregate_id"], event)

    if event == "mom_confirmed":
        # Dispatch fan-out: one row per destination already seeded in dispatch_targets.
        # PlaneAdapter / NotionAdapter create idempotently via dedup keys.
        _ = PlaneAdapter(settings), NotionAdapter(settings)
        # TODO(M4): per-destination create + store external_id + verify.
    elif event in {"created", "updated"}:
        pass  # TODO(M2): reindex into Qdrant; recompute derived todos/health.


async def run_once(settings) -> int:
    async with pool().acquire() as conn:
        async with conn.transaction():
            rows = await claim_batch(conn)
        for row in rows:
            try:
                await handle(row, settings)
                await conn.execute("UPDATE outbox SET status='done' WHERE id=$1", row["id"])
            except Exception as exc:  # requeue with backoff, dead-letter at the cap
                attempts = row["attempts"]
                status = "failed" if attempts < MAX_ATTEMPTS else "failed"
                await conn.execute(
                    "UPDATE outbox SET status=$2, last_error=$3, available_at=now() + ($4 || ' seconds')::interval WHERE id=$1",
                    row["id"], status, str(exc)[:500], str(backoff_seconds(attempts)),
                )
                log.warning("outbox id=%s failed (attempt %s): %s", row["id"], attempts, exc)
        return len(rows)


async def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    await init_pool()
    log.info("worker started env=%s", settings.env)
    try:
        while True:
            n = await run_once(settings)
            if n == 0:
                await asyncio.sleep(POLL_SECONDS)
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
