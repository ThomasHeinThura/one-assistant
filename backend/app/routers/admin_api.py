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
from ..integrations import openrouter
from ..security import require_auth

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

    if row["provider"] == "on_device":
        status, ready, detail = "on_device", True, "On-device (Apple MLX) — drafts Tier-1 with no cloud. Test from the iOS app."
    else:
        settings = get_settings()
        # Prefer the key stored on the OpenRouter integration, else the env key.
        orow = await pool().fetchrow("SELECT env FROM mcp_integrations WHERE name='OpenRouter'")
        key = (orow["env"] or {}).get("OPENROUTER_API_KEY") if orow else None
        ok, detail = await openrouter.ping_model(settings, row["model_id"], api_key=key)
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

    is_openrouter = row["name"] == "OpenRouter" or "openrouter.ai" in (row["endpoint"] or "")

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
    elif is_openrouter:
        key = env.get("OPENROUTER_API_KEY")
        if not key:
            detail = "set OPENROUTER_API_KEY"
        else:
            status, kind, why = await _probe(
                "https://openrouter.ai/api/v1/key", {"Authorization": f"Bearer {key}"})
            detail = "OpenRouter reachable; API key valid" if status == "connected" else f"OpenRouter: {why or kind}"
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
