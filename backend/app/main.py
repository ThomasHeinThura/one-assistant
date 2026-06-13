"""FastAPI app — CRM + visit + MoM + tickets + chat gateway for Maria One.

Security-relevant choices live here: strict CORS, security headers, no server
banner, request-size limits are enforced at the ingress (Cloudflare/Azure FD).
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .db import close_pool, init_pool
from .routers import admin_api, chat, clients, health, opportunities, tickets, today, visits

log = logging.getLogger("maria.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    await init_pool()
    log.info("API started env=%s", settings.env)
    yield
    await close_pool()


settings = get_settings()
app = FastAPI(title="Maria One API", version="0.1.0", lifespan=lifespan, docs_url=None if settings.is_prod else "/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,   # exact origins, never "*" in prod
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Cache-Control"] = "no-store"
    if settings.is_prod:
        resp.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    return resp


for r in (health.router, today.router, clients.router, visits.router,
          opportunities.router, tickets.router, chat.router, admin_api.router):
    app.include_router(r)

# Admin / config + workflow-workload UI (served only behind auth at the ingress).
_admin_dir = Path(__file__).parent / "admin"
if _admin_dir.exists():
    app.mount("/admin/static", StaticFiles(directory=_admin_dir), name="admin-static")

    @app.get("/admin", include_in_schema=False)
    async def admin_index() -> FileResponse:
        return FileResponse(_admin_dir / "index.html")
