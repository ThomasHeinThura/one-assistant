"""CRM pipeline: opportunities with AI health flags + stage history."""
from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..db import enqueue_outbox, pool, tx
from ..security import require_auth

router = APIRouter(prefix="/opportunities", tags=["crm"], dependencies=[Depends(require_auth)])

STALE_DAYS = 14  # no activity in N days -> at_risk (success criterion #3)


class OppIn(BaseModel):
    client_id: UUID
    title: str
    stage: str = "lead"
    pipeline_value_usd: float = 0
    target_close_date: date | None = None
    description: str | None = None


def compute_health(stage: str, last_activity_at) -> str:
    from datetime import datetime, timezone
    if stage in ("won", "lost"):
        return "healthy"
    if last_activity_at is None:
        return "watch"
    age = (datetime.now(timezone.utc) - last_activity_at).days
    if age >= STALE_DAYS:
        return "at_risk"
    return "watch" if age >= STALE_DAYS // 2 else "healthy"


@router.get("")
async def list_opps(filter: str = "all") -> list[dict]:
    rows = await pool().fetch("SELECT * FROM opportunities ORDER BY pipeline_value_usd DESC")
    out = [dict(r) for r in rows]
    if filter == "risk":
        out = [o for o in out if o["health"] == "at_risk"]
    elif filter in ("won", "lost"):
        out = [o for o in out if o["stage"] == filter]
    elif filter == "open":
        out = [o for o in out if o["stage"] not in ("won", "lost")]
    return out


@router.post("", status_code=201)
async def create_opp(body: OppIn) -> dict:
    async with tx() as conn:
        row = await conn.fetchrow(
            """INSERT INTO opportunities (client_id, title, stage, pipeline_value_usd, target_close_date, description, last_activity_at)
               VALUES ($1,$2,$3,$4,$5,$6, now()) RETURNING *""",
            body.client_id, body.title, body.stage, body.pipeline_value_usd, body.target_close_date, body.description,
        )
        await conn.execute(
            "INSERT INTO deal_stage_history (opportunity_id, to_stage) VALUES ($1,$2)", row["id"], body.stage
        )
        await enqueue_outbox(conn, aggregate="opportunity", aggregate_id=str(row["id"]), event="created")
    return dict(row)


@router.post("/{opp_id}/stage")
async def advance_stage(opp_id: UUID, to_stage: str, loss_reason: str | None = None) -> dict:
    async with tx() as conn:
        cur = await conn.fetchrow("SELECT stage FROM opportunities WHERE id=$1", opp_id)
        if not cur:
            raise HTTPException(404, "opportunity not found")
        status = "won" if to_stage == "won" else "lost" if to_stage == "lost" else "open"
        row = await conn.fetchrow(
            "UPDATE opportunities SET stage=$2, status=$3, loss_reason=$4, last_activity_at=now() WHERE id=$1 RETURNING *",
            opp_id, to_stage, status, loss_reason,
        )
        await conn.execute(
            "INSERT INTO deal_stage_history (opportunity_id, from_stage, to_stage) VALUES ($1,$2,$3)",
            opp_id, cur["stage"], to_stage,
        )
        await enqueue_outbox(conn, aggregate="opportunity", aggregate_id=str(opp_id), event="updated")
    return dict(row)
