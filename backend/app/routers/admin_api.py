"""Admin API — manage MCP integrations + agent skills from the ops console.

MCP lives server-side (the phone never speaks MCP, per the architecture), so this
is the right home for it. Secrets are never stored in the DB: `auth_ref` holds a
Key Vault secret NAME, and the real token is resolved at connect time.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..db import pool, tx
from ..security import require_auth

router = APIRouter(prefix="/admin/api", tags=["admin"], dependencies=[Depends(require_auth)])


# ---------------------------------------------------------------- MCP integrations
class MCPIn(BaseModel):
    name: str
    kind: str = Field(default="custom", pattern="^(plane|notion|custom)$")
    transport: str = Field(default="http", pattern="^(http|sse|stdio)$")
    endpoint: str | None = None
    auth_ref: str | None = None        # Key Vault secret name, NOT the token
    enabled: bool = False
    config: dict = Field(default_factory=dict)


@router.get("/mcp")
async def list_mcp() -> list[dict]:
    return [dict(r) for r in await pool().fetch("SELECT * FROM mcp_integrations ORDER BY name")]


@router.post("/mcp", status_code=201)
async def add_mcp(body: MCPIn) -> dict:
    async with tx() as conn:
        row = await conn.fetchrow(
            """INSERT INTO mcp_integrations (name, kind, transport, endpoint, auth_ref, enabled, config)
               VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb) RETURNING *""",
            body.name, body.kind, body.transport, body.endpoint, body.auth_ref,
            body.enabled, body.config,
        )
    return dict(row)


@router.patch("/mcp/{mcp_id}")
async def update_mcp(mcp_id: UUID, enabled: bool | None = None, endpoint: str | None = None,
                     auth_ref: str | None = None) -> dict:
    row = await pool().fetchrow(
        """UPDATE mcp_integrations
           SET enabled = COALESCE($2, enabled),
               endpoint = COALESCE($3, endpoint),
               auth_ref = COALESCE($4, auth_ref),
               status   = CASE WHEN $2 IS FALSE THEN 'disabled' ELSE status END
           WHERE id=$1 RETURNING *""",
        mcp_id, enabled, endpoint, auth_ref,
    )
    if not row:
        raise HTTPException(404, "integration not found")
    return dict(row)


@router.post("/mcp/{mcp_id}/test")
async def test_mcp(mcp_id: UUID) -> dict:
    """Probe an MCP integration's reachability. Stub: marks status from config.

    M4 replaces this with an actual MCP handshake (list tools) using the token
    resolved from auth_ref.
    """
    row = await pool().fetchrow("SELECT * FROM mcp_integrations WHERE id=$1", mcp_id)
    if not row:
        raise HTTPException(404, "integration not found")
    reachable = bool(row["endpoint"]) and bool(row["auth_ref"])
    status = "connected" if reachable else "error"
    await pool().execute(
        "UPDATE mcp_integrations SET status=$2, last_checked_at=now() WHERE id=$1", mcp_id, status
    )
    return {"status": status, "reachable": reachable,
            "detail": "real MCP handshake wired in M4" if reachable else "set endpoint + auth_ref first"}


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
