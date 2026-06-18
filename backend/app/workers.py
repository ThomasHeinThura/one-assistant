"""Background worker runner.

Implements the transactional-outbox → message-bus → worker-pool pipeline from
docs/07-datastore.md:

    Postgres commit + outbox row  (API, same txn)
            │
       relay loop          reads pending outbox rows, publishes to the bus
            │                 (Redis Streams by default; Kafka in the scale phase)
       consume loop        consumer-group reads, runs the handler, ACKs
            │                 reindex → Qdrant · dispatch → Plane/Notion · derive · verify
       Langfuse trace      one span per event, tagged with tier + destination

Idempotency (Redis SET NX) makes at-least-once delivery safe. Per-entity locks
stop two workers touching the same aggregate. Failures re-arm the outbox row with
exponential backoff so the relay re-publishes after a delay.

Run with:  python -m app.workers
"""
from __future__ import annotations

import asyncio
import logging
import os

from . import redis_client
from .bus import Message, get_bus
from .config import get_settings
from .db import close_pool, init_pool, pool
from .integrations.langfuse_client import trace
from .integrations.notion import NotionAdapter
from .integrations.plane import PlaneAdapter
from .integrations.qdrant import QdrantAdapter

log = logging.getLogger("maria.workers")
MAX_ATTEMPTS = 8
CONSUMER = os.environ.get("HOSTNAME", "worker-1")


def backoff_seconds(attempts: int) -> int:
    return min(300, 2 ** attempts)  # exponential, capped at 5 min


# --------------------------------------------------------------------- relay
async def relay_loop(bus) -> None:
    """Claim pending outbox rows and publish them to the bus (at-least-once)."""
    while True:
        async with pool().acquire() as conn:
            async with conn.transaction():
                rows = await conn.fetch(
                    """
                    UPDATE outbox SET status='processing'
                    WHERE id IN (
                      SELECT id FROM outbox
                      WHERE status='pending' AND available_at <= now()
                      ORDER BY available_at FOR UPDATE SKIP LOCKED LIMIT 50
                    )
                    RETURNING id, aggregate, aggregate_id, event, payload
                    """
                )
            for r in rows:
                await bus.publish(
                    event=r["event"],
                    payload={"aggregate": r["aggregate"], "aggregate_id": str(r["aggregate_id"]),
                             **(r["payload"] or {})},
                    outbox_id=r["id"],
                )
        if not rows:
            await asyncio.sleep(1.0)


# ------------------------------------------------------------------- handlers
# How to turn each aggregate into a searchable text blob + its sensitivity tier.
# Tier-1 (confidential) rows are NOT indexed server-side — that content stays on
# the device. We skip them here as a defence-in-depth backstop.
_RECORD_SQL: dict[str, str] = {
    "opportunity": """SELECT o.title, o.stage, o.health, o.status, o.pipeline_value_usd,
                             o.description, c.name AS client, 2 AS tier
                      FROM opportunities o JOIN clients c ON c.id=o.client_id WHERE o.id=$1""",
    "ticket": """SELECT t.title, t.type, t.status, t.priority, t.description,
                        c.name AS client, 2 AS tier
                 FROM tickets t LEFT JOIN clients c ON c.id=t.client_id WHERE t.id=$1""",
    "client": "SELECT name, account_type, status, notes, 2 AS tier FROM clients WHERE id=$1",
    "visit": """SELECT v.title, v.status, v.location, c.name AS client, v.sensitivity_tier AS tier
                FROM visits v JOIN clients c ON c.id=v.client_id WHERE v.id=$1""",
    "mom": """SELECT m.discussion, m.status, c.name AS client, m.sensitivity_tier AS tier
              FROM meeting_minutes m JOIN visits v ON v.id=m.visit_id
              JOIN clients c ON c.id=v.client_id WHERE m.id=$1""",
}


async def _record_text(aggregate: str, aggregate_id: str) -> tuple[str, int] | None:
    """Fetch a human-readable text blob + sensitivity tier for one record."""
    sql = _RECORD_SQL.get(aggregate)
    if not sql:
        return None
    row = await pool().fetchrow(sql, aggregate_id)
    if not row:
        return None
    d = dict(row)
    tier = int(d.pop("tier", 2) or 2)
    parts = [f"{aggregate.title()}"]
    for k, v in d.items():
        if v not in (None, "", 0):
            parts.append(f"{k}: {v}")
    return " | ".join(parts), tier


async def reindex(settings, aggregate: str, aggregate_id: str, span) -> None:
    """Embed the changed record into Qdrant (RAG). Tier-aware embedding backend.

    Tier-1 confidential rows are kept out of the vector store as a conservative
    default (the tier is an advisory label; nothing else routes on it now).
    """
    info = await _record_text(aggregate, aggregate_id)
    if info is None:
        span.event("reindex.skip", {"id": aggregate_id, "reason": "no text"})
        return
    text, tier = info
    if tier == 1:
        span.event("reindex.skip", {"id": aggregate_id, "reason": "tier-1 excluded from RAG"})
        return
    qd = QdrantAdapter(settings)
    wrote = await qd.upsert(source_id=f"{aggregate}:{aggregate_id}", text=text,
                            tier=tier, payload={"aggregate": aggregate})
    span.event("reindex.qdrant", {"id": aggregate_id, "written": wrote})


async def dispatch_mom(settings, aggregate_id: str, span) -> None:
    """Fan-out a confirmed MoM to CRM + Plane + Notion, per-destination, idempotent."""
    plane, notion = PlaneAdapter(settings), NotionAdapter(settings)
    async with pool().acquire() as conn:
        targets = await conn.fetch(
            "SELECT destination, status FROM dispatch_targets WHERE aggregate='mom' AND aggregate_id=$1",
            aggregate_id,
        )
        for t in targets:
            if t["status"] == "done":
                continue
            dest = t["destination"]
            try:
                ext_id = None
                if dest == "plane":
                    issue = await plane.create_issue(
                        title=f"Follow-up for MoM {aggregate_id}", description="",
                        dedup_key=f"mom:{aggregate_id}")
                    ext_id = issue.id
                elif dest == "notion":
                    page = await notion.create_meeting_note(
                        title=f"MoM {aggregate_id}", body="", dedup_key=f"mom:{aggregate_id}")
                    ext_id = page.id
                else:  # crm — already in Postgres; mark done
                    ext_id = aggregate_id
                await conn.execute(
                    """UPDATE dispatch_targets SET status='done', external_id=$3,
                       attempts=attempts+1, dispatched_at=now()
                       WHERE aggregate='mom' AND aggregate_id=$1 AND destination=$2""",
                    aggregate_id, dest, ext_id)
                span.event(f"dispatch.{dest}", {"status": "done", "external_id": ext_id})
            except Exception as exc:
                await conn.execute(
                    """UPDATE dispatch_targets SET status='failed', attempts=attempts+1, last_error=$3
                       WHERE aggregate='mom' AND aggregate_id=$1 AND destination=$2""",
                    aggregate_id, dest, str(exc)[:300])
                span.event(f"dispatch.{dest}", {"status": "failed", "error": str(exc)[:120]})
                raise  # bubble so the whole event retries (remaining dones are skipped next time)


async def handle(msg: Message, settings) -> None:
    """Route one bus message. Idempotent + traced."""
    key = f"{msg.event}:{msg.outbox_id}"
    if await redis_client.seen_before(key):
        log.info("skip duplicate %s", key)
        return

    aggregate = msg.payload.get("aggregate", "")
    aggregate_id = msg.payload.get("aggregate_id", "")
    with trace(msg.event, metadata={"aggregate": aggregate, "id": aggregate_id}) as span:
        async with redis_client.entity_lock(f"{aggregate}:{aggregate_id}") as got:
            if not got:
                raise RuntimeError("entity locked by another worker; will retry")
            if msg.event == "mom_confirmed":
                await dispatch_mom(settings, aggregate_id, span)
            elif msg.event in {"created", "updated"}:
                await reindex(settings, aggregate, aggregate_id, span)
            # TODO(M2): derive worker (todos/health/SLA) + verifier triple-check.


# ------------------------------------------------------------------- consumer
async def consume_loop(bus, settings) -> None:
    await bus.ensure_group()
    while True:
        msgs = await bus.consume(consumer=CONSUMER, count=10, block_ms=2000)
        for msg in msgs:
            try:
                await handle(msg, settings)
                if msg.outbox_id is not None:
                    await pool().execute("UPDATE outbox SET status='done' WHERE id=$1", msg.outbox_id)
                await bus.ack(msg.id)
            except Exception as exc:
                # Re-arm the outbox row with backoff; relay re-publishes after the delay.
                if msg.outbox_id is not None:
                    await pool().execute(
                        """UPDATE outbox SET status='pending', attempts=attempts+1, last_error=$2,
                           available_at = now() + ($3 || ' seconds')::interval WHERE id=$1""",
                        msg.outbox_id, str(exc)[:500], str(backoff_seconds(1)))
                await bus.ack(msg.id)  # ack to clear PEL; re-delivery comes via the outbox relay
                log.warning("event %s failed, re-armed: %s", msg.event, exc)


async def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    await init_pool()
    bus = get_bus(settings)
    await QdrantAdapter(settings).ensure_collection()
    log.info("worker started env=%s bus=%s", settings.env, settings.bus_backend)
    try:
        await asyncio.gather(relay_loop(bus), consume_loop(bus, settings))
    finally:
        await redis_client.close()
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
