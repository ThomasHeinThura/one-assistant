"""Clients + contacts CRUD (audit gap: CRM tab had no client/contact surface)."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..db import enqueue_outbox, pool, tx
from ..security import require_auth

router = APIRouter(prefix="/clients", tags=["clients"], dependencies=[Depends(require_auth)])


class ClientIn(BaseModel):
    name: str
    account_type: str | None = None
    address: str | None = None
    phone: str | None = None
    website: str | None = None
    notes: str | None = None


class ContactIn(BaseModel):
    name: str
    email: str | None = None
    phone: str | None = None
    position: str | None = None


@router.get("")
async def list_clients() -> list[dict]:
    rows = await pool().fetch("SELECT * FROM clients ORDER BY name")
    return [dict(r) for r in rows]


@router.post("", status_code=201)
async def create_client(body: ClientIn) -> dict:
    async with tx() as conn:
        row = await conn.fetchrow(
            """INSERT INTO clients (name, account_type, address, phone, website, notes)
               VALUES ($1,$2,$3,$4,$5,$6) RETURNING *""",
            body.name, body.account_type, body.address, body.phone, body.website, body.notes,
        )
        await enqueue_outbox(conn, aggregate="client", aggregate_id=str(row["id"]), event="created")
    return dict(row)


@router.get("/{client_id}")
async def get_client(client_id: UUID) -> dict:
    row = await pool().fetchrow("SELECT * FROM clients WHERE id=$1", client_id)
    if not row:
        raise HTTPException(404, "client not found")
    contacts = await pool().fetch("SELECT * FROM contacts WHERE client_id=$1 ORDER BY name", client_id)
    timeline = await pool().fetch(
        "SELECT * FROM timeline_events WHERE client_id=$1 ORDER BY created_at DESC LIMIT 50", client_id
    )
    return {**dict(row), "contacts": [dict(c) for c in contacts], "timeline": [dict(t) for t in timeline]}


@router.post("/{client_id}/contacts", status_code=201)
async def add_contact(client_id: UUID, body: ContactIn) -> dict:
    async with tx() as conn:
        row = await conn.fetchrow(
            """INSERT INTO contacts (client_id, name, email, phone, position)
               VALUES ($1,$2,$3,$4,$5) RETURNING *""",
            client_id, body.name, body.email, body.phone, body.position,
        )
    return dict(row)
