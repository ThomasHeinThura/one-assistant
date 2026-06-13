"""Maria quick-chat — a real OpenRouter answer grounded in live CRM context.

Maria pulls a compact snapshot of the CRM (counts + the most relevant rows) and
asks the pinned no-logging cloud model (Tier 2/3) to answer in her voice. If the
cloud is unreachable it falls back to a deterministic DB-derived answer so the
endpoint always responds. Confidential (Tier-1) drafting stays on-device — that
path runs in the iOS app, never here.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..config import get_settings
from ..db import pool
from ..integrations import openrouter
from ..security import require_auth

log = logging.getLogger("maria.chat")
router = APIRouter(prefix="/chat", tags=["ai"], dependencies=[Depends(require_auth)])


class Ask(BaseModel):
    question: str


SYSTEM = (
    "You are Maria, a concise sales & solution work assistant for a B2B team. "
    "You coordinate an in-house CRM, Plane (tickets) and Notion (notes). "
    "Answer in 1-3 short sentences, grounded ONLY in the CONTEXT provided. "
    "If the context doesn't contain the answer, say what you'd need to check. "
    "Be direct and practical; suggest a next action when useful."
)


async def _context() -> tuple[str, list[dict]]:
    """Compact live snapshot of the CRM for grounding + structured sources."""
    p = pool()
    clients = await p.fetchval("SELECT count(*) FROM clients")
    visits = await p.fetchval("SELECT count(*) FROM visits")
    open_tickets = await p.fetchval("SELECT count(*) FROM tickets WHERE status <> 'done'")
    at_risk = await p.fetch(
        "SELECT title, pipeline_value_usd FROM opportunities WHERE health='at_risk' ORDER BY pipeline_value_usd DESC LIMIT 5"
    )
    todos = await p.fetch(
        "SELECT title FROM todos WHERE status <> 'done' ORDER BY priority DESC, created_at DESC LIMIT 8"
    )

    lines = [
        f"clients={clients}, visits={visits}, open_tickets={open_tickets}",
        f"at_risk_deals={len(at_risk)}: " + "; ".join(
            f"{r['title']} (${r['pipeline_value_usd']:,})" for r in at_risk
        ) if at_risk else "at_risk_deals=0",
        "open_todos: " + ("; ".join(r["title"] for r in todos) if todos else "none"),
    ]
    sources = [dict(r) for r in at_risk]
    return "\n".join(lines), sources


@router.post("")
async def ask(body: Ask) -> dict:
    settings = get_settings()
    context, sources = await _context()

    # Prefer the key stored on the OpenRouter integration row, else the env key.
    orow = await pool().fetchrow("SELECT env FROM mcp_integrations WHERE name='OpenRouter'")
    key = (orow["env"] or {}).get("OPENROUTER_API_KEY") if orow else None

    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"CONTEXT:\n{context}\n\nQUESTION: {body.question}"},
    ]
    try:
        answer = await openrouter.complete(settings, messages, api_key=key, max_tokens=400)
        return {"answer": answer, "sources": sources, "model": "openrouter", "grounded": True}
    except Exception as exc:
        log.warning("chat cloud fallback: %s", exc)

    # Deterministic fallback so the endpoint always answers, even cloud-down.
    q = body.question.lower()
    if "at-risk" in q or "at risk" in q:
        return {"answer": f"{len(sources)} at-risk deals right now." +
                (" Top: " + sources[0]["title"] if sources else ""),
                "sources": sources, "model": "fallback", "grounded": True}
    return {"answer": "Maria's cloud model is unavailable right now — check the OpenRouter key in "
                      "the admin console. I can still answer from CRM data once it's back.",
            "sources": sources, "model": "fallback", "grounded": False}
