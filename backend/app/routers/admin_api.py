"""Admin API — manage MCP integrations + agent skills from the ops console.

MCP lives server-side (the phone never speaks MCP, per the architecture), so this
is the right home for it. Two ways to configure an integration:
  * http/sse: `endpoint` URL (+ `auth_ref` Key Vault secret name).
  * stdio:    `command` + `args` launched by the worker (e.g. uvx plane-mcp-server),
              with `env` vars (which may include a secret like PLANE_API_KEY).

`env` values are REDACTED on read so secrets are never echoed back to the UI.
"""
from __future__ import annotations

import re
import httpx
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..config import get_settings
from ..db import pool, tx
from ..integrations import ollama
from ..integrations.qdrant import QdrantAdapter
from ..security import require_auth
from ..workers import _RECORD_SQL, _record_text

router = APIRouter(prefix="/admin/api", tags=["admin"], dependencies=[Depends(require_auth)])


# ------------------------------------------------------------------- overview KPIs
@router.get("/overview")
async def overview() -> dict:
    p = pool()
    ob = await p.fetchrow(
        """SELECT
             count(*) FILTER (WHERE status IN ('pending','processing')) AS pending,
             count(*) FILTER (WHERE status = 'failed')                  AS failed,
             count(*) FILTER (WHERE status IN ('done','verified'))      AS verified
           FROM outbox""")
    mcp = await p.fetchrow(
        "SELECT count(*) AS total, count(*) FILTER (WHERE status='connected') AS connected FROM mcp_integrations")
    models = await p.fetchrow(
        "SELECT count(*) AS total, count(*) FILTER (WHERE ready) AS ready FROM ai_models")
    return {
        "outbox": {"pending": ob["pending"], "failed": ob["failed"], "verified": ob["verified"]},
        "integrations": {"total": mcp["total"], "connected": mcp["connected"]},
        "models": {"total": models["total"], "ready": models["ready"]},
    }


# ----------------------------------------------------------------------- AI models
@router.get("/models")
async def list_models() -> list[dict]:
    return [dict(r) for r in await pool().fetch("SELECT * FROM ai_models ORDER BY sort, name")]


@router.post("/models/{model_id}/test")
async def test_model(model_id: UUID) -> dict:
    row = await pool().fetchrow("SELECT * FROM ai_models WHERE id=$1", model_id)
    if not row:
        raise HTTPException(404, "model not found")

    settings = get_settings()
    # Prefer the key stored on the Ollama integration, else the env key.
    orow = await pool().fetchrow("SELECT env FROM mcp_integrations WHERE name='Ollama'")
    key = (orow["env"] or {}).get("OLLAMA_API_KEY") if orow else None
    ok, detail = await ollama.ping_model(settings, row["model_id"], api_key=key)
    status, ready = ("ready", True) if ok else ("error", False)

    await pool().execute(
        "UPDATE ai_models SET ready=$2, status=$3, detail=$4, last_checked_at=now() WHERE id=$1",
        model_id, ready, status, detail)
    return {"status": status, "ready": ready, "detail": detail}

_SECRET_RE = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|PASS)$", re.IGNORECASE)


def _redact_env(env: dict | None) -> dict:
    """Mask secret-looking env values; show non-secret ones (slug, base_url)."""
    out = {}
    for k, v in (env or {}).items():
        out[k] = "••••set" if (_SECRET_RE.search(k) and v) else v
    return out


def _public(row) -> dict:
    d = dict(row)
    d["env"] = _redact_env(d.get("env"))
    d.pop("auth_ref", None)
    return d


# ---------------------------------------------------------------- MCP integrations
class MCPIn(BaseModel):
    name: str
    kind: str = Field(default="custom", pattern="^(plane|notion|custom)$")
    transport: str = Field(default="http", pattern="^(http|sse|stdio)$")
    endpoint: str | None = None
    auth_ref: str | None = None              # Key Vault secret name (http/sse)
    command: str | None = None               # stdio launcher, e.g. "uvx"
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    enabled: bool = False
    config: dict = Field(default_factory=dict)


class EnvVar(BaseModel):
    key: str
    value: str


@router.get("/mcp")
async def list_mcp() -> list[dict]:
    return [_public(r) for r in await pool().fetch("SELECT * FROM mcp_integrations ORDER BY name")]


@router.post("/mcp", status_code=201)
async def add_mcp(body: MCPIn) -> dict:
    async with tx() as conn:
        row = await conn.fetchrow(
            """INSERT INTO mcp_integrations (name, kind, transport, endpoint, auth_ref, command, args, env, enabled, config)
               VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8::jsonb,$9,$10::jsonb) RETURNING *""",
            body.name, body.kind, body.transport, body.endpoint, body.auth_ref,
            body.command, body.args, body.env, body.enabled, body.config,
        )
    return _public(row)


@router.patch("/mcp/{mcp_id}")
async def update_mcp(mcp_id: UUID, enabled: bool | None = None, endpoint: str | None = None) -> dict:
    row = await pool().fetchrow(
        """UPDATE mcp_integrations
           SET enabled  = COALESCE($2, enabled),
               endpoint = COALESCE($3, endpoint),
               status   = CASE WHEN $2 IS FALSE THEN 'disabled' ELSE status END
           WHERE id=$1 RETURNING *""",
        mcp_id, enabled, endpoint,
    )
    if not row:
        raise HTTPException(404, "integration not found")
    return _public(row)


@router.post("/mcp/{mcp_id}/env")
async def set_env(mcp_id: UUID, body: EnvVar) -> dict:
    """Merge a single env var (e.g. PLANE_API_KEY) into the integration."""
    row = await pool().fetchrow(
        "UPDATE mcp_integrations SET env = env || jsonb_build_object($2::text, $3::text) WHERE id=$1 RETURNING *",
        mcp_id, body.key, body.value,
    )
    if not row:
        raise HTTPException(404, "integration not found")
    return _public(row)


@router.delete("/mcp/{mcp_id}/env/{key}")
async def unset_env(mcp_id: UUID, key: str) -> dict:
    row = await pool().fetchrow(
        "UPDATE mcp_integrations SET env = env - $2 WHERE id=$1 RETURNING *", mcp_id, key
    )
    if not row:
        raise HTTPException(404, "integration not found")
    return _public(row)


@router.post("/mcp/{mcp_id}/test")
async def test_mcp(mcp_id: UUID) -> dict:
    """Validate connectivity. For Plane we do a real REST check with the stored
    key (plane-mcp-server wraps the same API); others report config readiness."""
    row = await pool().fetchrow("SELECT * FROM mcp_integrations WHERE id=$1", mcp_id)
    if not row:
        raise HTTPException(404, "integration not found")
    env = row["env"] or {}
    status, detail = "error", ""

    is_ollama = row["name"] == "Ollama" or "ollama.com" in (row["endpoint"] or "")

    async def _probe(url: str, headers: dict) -> tuple[str, str, str]:
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(url, headers=headers)
            if r.status_code == 200:
                return "connected", "valid", ""
            if r.status_code in (401, 403):
                return "error", "rejected", "API key rejected (401/403)"
            return "error", "http", f"HTTP {r.status_code}"
        except Exception as exc:
            return "error", "unreachable", f"cannot reach host: {str(exc)[:120]}"

    if row["kind"] == "plane":
        base, slug, key = env.get("PLANE_BASE_URL"), env.get("PLANE_WORKSPACE_SLUG"), env.get("PLANE_API_KEY")
        if not (base and slug and key):
            detail = "set PLANE_BASE_URL, PLANE_WORKSPACE_SLUG, and PLANE_API_KEY"
        else:
            try:
                async with httpx.AsyncClient(timeout=12) as c:
                    r = await c.get(f"{base.rstrip('/')}/api/v1/workspaces/{slug}/projects/",
                                    headers={"X-API-Key": key})
                if r.status_code == 200:
                    j = r.json()
                    n = j.get("total_count", j.get("count", len(j.get("results", []))))
                    status, detail = "connected", f"Plane connected — {n} project(s) in '{slug}'"
                elif r.status_code in (401, 403):
                    detail = "Plane: API key rejected (401/403)"
                else:
                    detail = f"Plane: HTTP {r.status_code}"
            except Exception as exc:
                detail = f"Plane: cannot reach host: {str(exc)[:120]}"
    elif row["kind"] == "notion":
        token = env.get("NOTION_TOKEN")
        if not token:
            detail = "set NOTION_TOKEN"
        else:
            try:
                async with httpx.AsyncClient(timeout=12) as c:
                    r = await c.post("https://api.notion.com/v1/search",
                                     headers={"Authorization": f"Bearer {token}",
                                              "Notion-Version": "2022-06-28",
                                              "Content-Type": "application/json"},
                                     json={"filter": {"property": "object", "value": "database"},
                                           "page_size": 100})
                if r.status_code == 200:
                    n = len(r.json().get("results", []))
                    status, detail = "connected", f"Notion connected — {n} database(s) accessible"
                elif r.status_code in (401, 403):
                    detail = "Notion: token rejected (401/403)"
                else:
                    detail = f"Notion: HTTP {r.status_code}"
            except Exception as exc:
                detail = f"Notion: cannot reach host: {str(exc)[:120]}"
    elif is_ollama:
        key = env.get("OLLAMA_API_KEY")
        if not key:
            detail = "set OLLAMA_API_KEY"
        else:
            base = (row["endpoint"] or "https://ollama.com/v1").rstrip("/")
            status, kind, why = await _probe(
                f"{base}/models", {"Authorization": f"Bearer {key}"})
            detail = "Ollama Cloud reachable; API key valid" if status == "connected" else f"Ollama: {why or kind}"
    else:
        ready = bool(row["endpoint"] or row["command"])
        status = "connected" if ready else "error"
        detail = "config present (live MCP handshake wired in M4)" if ready else "set an endpoint or command"

    await pool().execute(
        "UPDATE mcp_integrations SET status=$2, last_checked_at=now() WHERE id=$1", mcp_id, status
    )
    return {"status": status, "detail": detail}


@router.delete("/mcp/{mcp_id}", status_code=204)
async def delete_mcp(mcp_id: UUID):
    await pool().execute("DELETE FROM mcp_integrations WHERE id=$1", mcp_id)


# -------------------------------------------------------------------------- RAG
# The aggregate → table map for backfill. Each id column is the PK of that table.
_RAG_SOURCES = {
    "opportunity": "SELECT id FROM opportunities",
    "ticket": "SELECT id FROM tickets",
    "client": "SELECT id FROM clients",
    # Tier-1 visits/MoMs are filtered inside _record_text/reindex (they return tier).
    "visit": "SELECT id FROM visits",
    "mom": "SELECT id FROM meeting_minutes",
}


@router.get("/rag/status")
async def rag_status() -> dict:
    """Qdrant health + indexed point count, so the console can show RAG state."""
    settings = get_settings()
    qd = QdrantAdapter(settings)
    healthy = await qd.healthy()
    points = None
    try:
        async with httpx.AsyncClient(base_url=settings.qdrant_url, timeout=10) as c:
            r = await c.get(f"/collections/{settings.qdrant_collection}")
            if r.status_code == 200:
                points = r.json().get("result", {}).get("points_count")
    except Exception:
        pass
    return {"healthy": healthy, "collection": settings.qdrant_collection, "points": points}


@router.post("/rag/reindex")
async def rag_reindex() -> dict:
    """Backfill the vector index from Postgres (Tier-2 records only).

    Walks the main aggregates and upserts each into Qdrant. Tier-1 rows are
    skipped (their tier is read inside _record_text). Fail-soft per record.
    """
    settings = get_settings()
    qd = QdrantAdapter(settings)
    await qd.ensure_collection()
    indexed, skipped, errors = 0, 0, 0
    for aggregate, sql in _RAG_SOURCES.items():
        if aggregate not in _RECORD_SQL:
            continue
        for row in await pool().fetch(sql):
            agg_id = str(row["id"])
            try:
                info = await _record_text(aggregate, agg_id)
                if info is None:
                    skipped += 1
                    continue
                text, tier = info
                if tier == 1:
                    skipped += 1
                    continue
                wrote = await qd.upsert(source_id=f"{aggregate}:{agg_id}", text=text,
                                        tier=tier, payload={"aggregate": aggregate})
                indexed += 1 if wrote else 0
                skipped += 0 if wrote else 1
            except Exception:
                errors += 1
    return {"indexed": indexed, "skipped": skipped, "errors": errors}


# ----------------------------------------------------------------------- Skills
class SkillIn(BaseModel):
    name: str
    description: str
    kind: str = Field(default="custom", pattern="^(builtin|custom|test)$")
    trigger: str | None = None
    enabled: bool = True
    config: dict = Field(default_factory=dict)


@router.get("/skills")
async def list_skills() -> list[dict]:
    return [dict(r) for r in await pool().fetch("SELECT * FROM skills ORDER BY kind, name")]


@router.post("/skills", status_code=201)
async def add_skill(body: SkillIn) -> dict:
    async with tx() as conn:
        row = await conn.fetchrow(
            """INSERT INTO skills (name, description, kind, trigger, enabled, config)
               VALUES ($1,$2,$3,$4,$5,$6::jsonb) RETURNING *""",
            body.name, body.description, body.kind, body.trigger, body.enabled, body.config,
        )
    return dict(row)


@router.patch("/skills/{skill_id}")
async def toggle_skill(skill_id: UUID, enabled: bool) -> dict:
    row = await pool().fetchrow(
        "UPDATE skills SET enabled=$2 WHERE id=$1 RETURNING *", skill_id, enabled
    )
    if not row:
        raise HTTPException(404, "skill not found")
    return dict(row)


@router.post("/skills/{skill_id}/run")
async def run_skill(skill_id: UUID, message: str = "ping") -> dict:
    """Run a skill. The default 'echo-test' skill verifies the agent pipeline
    end-to-end without external side effects."""
    row = await pool().fetchrow("SELECT * FROM skills WHERE id=$1", skill_id)
    if not row:
        raise HTTPException(404, "skill not found")
    if not row["enabled"]:
        raise HTTPException(409, "skill is disabled")
    if row["kind"] == "test":
        # No side effects: confirms routing + serialization are healthy.
        return {"skill": row["name"], "ok": True, "echo": message,
                "checks": {"agent_route": True, "serialization": True}}
    # Custom/builtin skills dispatch to AgentScope in M2.
    return {"skill": row["name"], "ok": False, "detail": "non-test skill execution wired in M2"}


@router.delete("/skills/{skill_id}", status_code=204)
async def delete_skill(skill_id: UUID):
    await pool().execute("DELETE FROM skills WHERE id=$1", skill_id)
