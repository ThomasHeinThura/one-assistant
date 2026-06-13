"""Today brief + AI-prioritised to-dos (the home tab)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..db import pool, tx
from ..security import require_auth

router = APIRouter(prefix="/today", tags=["today"], dependencies=[Depends(require_auth)])


class TodoIn(BaseModel):
    title: str
    due_date: str | None = None


@router.get("")
async def today_brief() -> dict:
    p = pool()
    visits = await p.fetchval(
        "SELECT count(*) FROM visits WHERE visit_date = current_date AND status <> 'missed'"
    )
    at_risk = await p.fetchval("SELECT count(*) FROM opportunities WHERE health='at_risk'")
    healthy = await p.fetchval("SELECT count(*) FROM opportunities WHERE health='healthy'")
    tickets_to_action = await p.fetchval(
        "SELECT count(*) FROM tickets WHERE status IN ('new','blocked') OR assignee_id IS NULL"
    )
    todos = await p.fetch("SELECT * FROM todos WHERE status <> 'done' ORDER BY priority DESC, created_at LIMIT 20")
    return {
        "glance": {
            "visits_today": visits,
            "tickets_to_action": tickets_to_action,
            "healthy_deals": healthy,
            "at_risk_deals": at_risk,
        },
        "todos": [dict(t) for t in todos],
    }


@router.post("/todos", status_code=201)
async def add_todo(body: TodoIn) -> dict:
    # source='user' so derive workers never overwrite it (audit gap #7).
    async with tx() as conn:
        row = await conn.fetchrow(
            "INSERT INTO todos (title, due_date, source) VALUES ($1, $2::date, 'user') RETURNING *",
            body.title, body.due_date,
        )
    return dict(row)
