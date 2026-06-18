"""VisitPlan: plan, GPS check-in/out, agenda checklist, MoM confirm + dispatch.

These endpoints cover the audit gaps the UI mockup was missing: GPS check-in,
agenda checklist tick-off, a structured MoM with a review/confirm step, the
sensitivity tier, and per-destination dispatch fan-out.
"""
from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..db import enqueue_outbox, pool, tx
from ..security import require_auth

router = APIRouter(prefix="/visits", tags=["visits"], dependencies=[Depends(require_auth)])


class VisitIn(BaseModel):
    title: str
    client_id: UUID
    contact_id: UUID | None = None
    visit_date: date | None = None
    location: str | None = None
    sensitivity_tier: int = Field(default=2, ge=1, le=3)
    agenda: list[str] = Field(default_factory=list)


class CheckIn(BaseModel):
    lat: float
    lng: float


class MoMIn(BaseModel):
    attendees: list[str] = Field(default_factory=list)
    discussion: str | None = None
    decisions: list[str] = Field(default_factory=list)
    next_visit_date: date | None = None
    drafted_by: str = Field(default="cloud", pattern="^(on_device|cloud)$")  # cloud only now; pattern kept for back-compat
    action_items: list[dict] = Field(default_factory=list)  # {description, owner_id?, due_date?}


@router.get("")
async def list_visits() -> list[dict]:
    rows = await pool().fetch("SELECT * FROM visits ORDER BY visit_date NULLS LAST, start_time")
    return [dict(r) for r in rows]


@router.post("", status_code=201)
async def plan_visit(body: VisitIn) -> dict:
    async with tx() as conn:
        v = await conn.fetchrow(
            """INSERT INTO visits (title, client_id, contact_id, visit_date, location, sensitivity_tier)
               VALUES ($1,$2,$3,$4,$5,$6) RETURNING *""",
            body.title, body.client_id, body.contact_id, body.visit_date, body.location, body.sensitivity_tier,
        )
        for i, item in enumerate(body.agenda):
            await conn.execute(
                "INSERT INTO agenda_items (visit_id, title, sort_order) VALUES ($1,$2,$3)",
                v["id"], item, i,
            )
        await enqueue_outbox(conn, aggregate="visit", aggregate_id=str(v["id"]), event="created")
    return dict(v)


@router.post("/{visit_id}/checkin")
async def checkin(visit_id: UUID, body: CheckIn) -> dict:
    row = await pool().fetchrow(
        """UPDATE visits SET status='in_progress', checkin_at=now(), checkin_lat=$2, checkin_lng=$3
           WHERE id=$1 RETURNING *""",
        visit_id, body.lat, body.lng,
    )
    if not row:
        raise HTTPException(404, "visit not found")
    return dict(row)


@router.post("/{visit_id}/checkout")
async def checkout(visit_id: UUID) -> dict:
    row = await pool().fetchrow(
        "UPDATE visits SET status='completed', checkout_at=now() WHERE id=$1 RETURNING *", visit_id
    )
    if not row:
        raise HTTPException(404, "visit not found")
    return dict(row)


@router.patch("/agenda/{item_id}")
async def toggle_agenda(item_id: UUID, completed: bool) -> dict:
    row = await pool().fetchrow(
        "UPDATE agenda_items SET completed=$2 WHERE id=$1 RETURNING *", item_id, completed
    )
    if not row:
        raise HTTPException(404, "agenda item not found")
    return dict(row)


@router.post("/{visit_id}/mom", status_code=201)
async def upsert_mom(visit_id: UUID, body: MoMIn) -> dict:
    """Save a DRAFT MoM. Nothing is dispatched yet.

    All drafting now happens in the cloud (Ollama Cloud); the on-device path was
    removed, so there is no Tier-1 cloud restriction here anymore.
    """
    visit = await pool().fetchrow("SELECT sensitivity_tier FROM visits WHERE id=$1", visit_id)
    if not visit:
        raise HTTPException(404, "visit not found")
    tier = visit["sensitivity_tier"]
    async with tx() as conn:
        mom = await conn.fetchrow(
            """INSERT INTO meeting_minutes
                 (visit_id, attendees, discussion, decisions, next_visit_date, drafted_by, sensitivity_tier)
               VALUES ($1,$2::jsonb,$3,$4::jsonb,$5,$6,$7) RETURNING *""",
            visit_id, body.attendees, body.discussion, body.decisions,
            body.next_visit_date, body.drafted_by, tier,
        )
        for ai in body.action_items:
            await conn.execute(
                "INSERT INTO action_items (mom_id, description, owner_id, due_date) VALUES ($1,$2,$3,$4)",
                mom["id"], ai.get("description", ""), ai.get("owner_id"), ai.get("due_date"),
            )
    return dict(mom)


@router.post("/mom/{mom_id}/confirm")
async def confirm_mom(mom_id: UUID) -> dict:
    """Confirm the MoM and enqueue the three-destination fan-out (idempotent).

    Seeds one dispatch_targets row per destination so partial failure is visible
    and re-runs never double-create.
    """
    async with tx() as conn:
        mom = await conn.fetchrow(
            "UPDATE meeting_minutes SET status='confirmed', confirmed_at=now() WHERE id=$1 RETURNING *",
            mom_id,
        )
        if not mom:
            raise HTTPException(404, "MoM not found")
        for dest in ("crm", "plane", "notion"):
            await conn.execute(
                """INSERT INTO dispatch_targets (aggregate, aggregate_id, destination)
                   VALUES ('mom',$1,$2) ON CONFLICT (aggregate, aggregate_id, destination) DO NOTHING""",
                mom_id, dest,
            )
        await enqueue_outbox(
            conn, aggregate="mom", aggregate_id=str(mom_id), event="mom_confirmed",
            idempotency_key=f"mom_confirmed:{mom_id}",
        )
    return {"status": "confirmed", "mom_id": str(mom_id)}


@router.get("/mom/{mom_id}/dispatch")
async def dispatch_status(mom_id: UUID) -> list[dict]:
    rows = await pool().fetch(
        "SELECT destination, status, external_id, attempts, last_error, dispatched_at "
        "FROM dispatch_targets WHERE aggregate='mom' AND aggregate_id=$1",
        mom_id,
    )
    return [dict(r) for r in rows]
