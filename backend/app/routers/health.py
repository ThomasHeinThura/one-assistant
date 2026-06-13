"""Liveness + readiness. Azure Container Apps / k8s probe these."""
from __future__ import annotations

from fastapi import APIRouter

from .. import redis_client
from ..bus import get_bus
from ..config import get_settings
from ..db import pool
from ..integrations.qdrant import QdrantAdapter

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict:
    """Liveness — process is up."""
    return {"status": "ok"}


@router.get("/readyz")
async def readyz() -> dict:
    """Readiness — dependencies reachable."""
    settings = get_settings()
    checks: dict[str, bool] = {}
    try:
        async with pool().acquire() as conn:
            await conn.execute("SELECT 1")
        checks["postgres"] = True
    except Exception:
        checks["postgres"] = False
    checks["qdrant"] = await QdrantAdapter(settings).healthy()
    checks["redis"] = await redis_client.ping()
    bus_depth = await get_bus(settings).depth()
    ready = checks["postgres"]  # Postgres is the only hard dependency for readiness
    return {"ready": ready, "checks": checks, "bus": {"backend": settings.bus_backend, "depth": bus_depth}}
