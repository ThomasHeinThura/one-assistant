"""Maria quick-chat — a real Ollama Cloud answer grounded in live CRM context.

Maria pulls a compact snapshot of the CRM (counts + the most relevant rows) and
asks the pinned cloud model to answer in her voice. If the cloud is unreachable it
falls back to a deterministic DB-derived answer so the endpoint always responds.
All AI runs in the cloud now (Ollama Cloud); there is no on-device path.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..config import get_settings
from ..db import pool
from ..integrations import ollama
from ..integrations.qdrant import QdrantAdapter
from ..security import require_auth

log = logging.getLogger("maria.chat")
router = APIRouter(prefix="/chat", tags=["ai"], dependencies=[Depends(require_auth)])


class Ask(BaseModel):
    question: str
    skill: str | None = None   # optional skill slug: project-manager | sales-manager | coordination | presentation


SYSTEM = (
    "You are Maria, a concise sales & solution work assistant for a B2B team. "
    "You coordinate an in-house CRM, Plane (tickets) and Notion (notes). "
    "Answer in 1-3 short sentences, grounded ONLY in the CONTEXT provided. "
    "If the context doesn't contain the answer, say what you'd need to check. "
    "Be direct and practical; suggest a next action when useful."
)


async def _context(question: str, settings) -> tuple[str, list[dict]]:
    """Grounding context for the question: a compact live CRM snapshot PLUS the
    top RAG passages retrieved from Qdrant for this specific question.

    RAG is fail-soft — if Qdrant or the embedder is unavailable, we still return
    the live snapshot so the endpoint always has something to ground on. Tier-2
    only: Tier-1 content is never indexed server-side.
    """
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

    # Semantic retrieval over indexed CRM records (Tier-2 RAG).
    hits = await QdrantAdapter(settings).search(question, limit=4, tier=2)
    if hits:
        lines.append("\nRELEVANT RECORDS (retrieved):")
        for h in hits:
            if h.get("text"):
                lines.append(f"- {h['text']}")
        sources += [{"source_id": h.get("source_id"), "score": h.get("score")} for h in hits]

    return "\n".join(lines), sources


async def _skill_prompt(slug: str | None) -> str | None:
    """Load an enabled skill's system prompt (config.prompt) by slug."""
    if not slug:
        return None
    row = await pool().fetchrow(
        "SELECT config FROM skills WHERE name=$1 AND enabled = true", slug
    )
    if not row:
        return None
    cfg = row["config"] or {}
    return cfg.get("prompt")


@router.post("")
async def ask(body: Ask) -> dict:
    settings = get_settings()
    context, sources = await _context(body.question, settings)

    # Prefer the key stored on the Ollama integration row, else the env key.
    orow = await pool().fetchrow("SELECT env FROM mcp_integrations WHERE name='Ollama'")
    key = (orow["env"] or {}).get("OLLAMA_API_KEY") if orow else None

    # A selected skill swaps in its specialised system prompt (PM / sales / etc).
    system = await _skill_prompt(body.skill) or SYSTEM
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"CONTEXT:\n{context}\n\nQUESTION: {body.question}"},
    ]
    rate_limited = False
    try:
        answer = await ollama.complete(settings, messages, api_key=key, max_tokens=400)
        model_id = (settings.ollama_models[0] if settings.ollama_models else "ollama")
        return {"answer": answer, "sources": sources, "model": model_id, "grounded": True}
    except Exception as exc:
        log.warning("chat cloud fallback: %s", exc)
        rate_limited = "rate_limited" in str(exc)

    # Deterministic fallback so the endpoint always answers, even cloud-down.
    q = body.question.lower()
    note = (" (Maria's free cloud model hit its Ollama rate limit — retry shortly, or upgrade "
            "the Ollama plan for always-on AI replies.)") if rate_limited else ""
    if "at-risk" in q or "at risk" in q:
        top = (" Top: " + sources[0]["title"]) if sources else ""
        return {"answer": f"{len(sources)} at-risk deal(s) right now.{top}{note}",
                "sources": sources, "model": "fallback", "grounded": True}
    if "ticket" in q:
        return {"answer": f"I track open tickets from Plane.{note}",
                "sources": sources, "model": "fallback", "grounded": True}
    msg = ("Maria's free cloud model hit its Ollama rate limit — please retry in a moment. "
           "Upgrade the Ollama plan for reliable replies." if rate_limited
           else "Maria's cloud model is unavailable — check the Ollama key in the admin console.")
    return {"answer": msg, "sources": sources, "model": "fallback", "grounded": False}
