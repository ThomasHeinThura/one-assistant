"""Tickets: create + assign, AND read/detail (audit gap: UI had no 'check ticket' view).

Per the per-object SoT decision, Plane is authoritative for status. Local creates
start sync_source='local'; an inbound Plane pull flips sync_source='plane' and the
verifier then treats Plane as the truth (never re-pushes over a teammate edit).
"""
from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..db import enqueue_outbox, pool, tx
from ..security import require_auth

router = APIRouter(prefix="/tickets", tags=["tickets"], dependencies=[Depends(require_auth)])


class TicketIn(BaseModel):
    title: str
    type: str = "managed_service"
    client_id: UUID | None = None
    project_id: UUID | None = None
    priority: str = "normal"
    assignee_id: UUID | None = None
    description: str | None = None
    due_date: date | None = None


@router.get("")
async def list_tickets(status: str | None = None, client_id: UUID | None = None) -> list[dict]:
    sql = "SELECT * FROM tickets WHERE 1=1"
    args: list = []
    if status:
        args.append(status); sql += f" AND status=${len(args)}"
    if client_id:
        args.append(client_id); sql += f" AND client_id=${len(args)}"
    sql += " ORDER BY updated_at DESC"
    return [dict(r) for r in await pool().fetch(sql, *args)]


@router.get("/{ticket_id}")
async def get_ticket(ticket_id: UUID) -> dict:
    """The 'check the ticket' detail view that the UI mockup lacked."""
    row = await pool().fetchrow("SELECT * FROM tickets WHERE id=$1", ticket_id)
    if not row:
        raise HTTPException(404, "ticket not found")
    return dict(row)


@router.post("", status_code=201)
async def create_ticket(body: TicketIn) -> dict:
    async with tx() as conn:
        row = await conn.fetchrow(
            """INSERT INTO tickets (title, type, client_id, project_id, priority, assignee_id, description, due_date)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING *""",
            body.title, body.type, body.client_id, body.project_id, body.priority,
            body.assignee_id, body.description, body.due_date,
        )
        # Outbox -> dispatch worker creates the Plane issue idempotently + reindexes into RAG.
        await enqueue_outbox(
            conn, aggregate="ticket", aggregate_id=str(row["id"]), event="created",
            idempotency_key=f"ticket_create:{row['id']}",
        )
    return dict(row)


@router.post("/{ticket_id}/assign")
async def assign_ticket(ticket_id: UUID, assignee_id: UUID) -> dict:
    async with tx() as conn:
        row = await conn.fetchrow(
            "UPDATE tickets SET assignee_id=$2, status='assigned' WHERE id=$1 RETURNING *",
            ticket_id, assignee_id,
        )
        if not row:
            raise HTTPException(404, "ticket not found")
        await enqueue_outbox(conn, aggregate="ticket", aggregate_id=str(ticket_id), event="updated")
    return dict(row)
