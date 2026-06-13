"""Maria quick-chat (RAG-grounded). Skeleton returns a structured stub; M2 wires
the AgentScope coordinator + Qdrant retrieval behind the same contract."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..db import pool
from ..security import require_auth

router = APIRouter(prefix="/chat", tags=["ai"], dependencies=[Depends(require_auth)])


class Ask(BaseModel):
    question: str


@router.post("")
async def ask(body: Ask) -> dict:
    """Answer across CRM/visits/tickets.

    Skeleton: deterministic answers from live DB counts so the contract is real
    and testable. M2 replaces the body with AgentScope + Qdrant retrieval.
    """
    q = body.question.lower()
    p = pool()
    if "at-risk" in q or "at risk" in q:
        rows = await p.fetch(
            "SELECT title, pipeline_value_usd FROM opportunities WHERE health='at_risk' ORDER BY pipeline_value_usd DESC"
        )
        return {"answer": f"{len(rows)} at-risk deals.", "sources": [dict(r) for r in rows]}
    if "ticket" in q:
        rows = await p.fetch("SELECT title, status, plane_issue_id FROM tickets WHERE status <> 'done'")
        return {"answer": f"{len(rows)} open tickets.", "sources": [dict(r) for r in rows]}
    return {"answer": "Checking across CRM, visits, and tickets… (RAG wired in M2).", "sources": []}
