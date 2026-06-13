"""Admin console login — username/password → bearer token.

Operators sign in with a username + password (stored as a pbkdf2 hash in
admin_users); on success the console receives the API bearer token to use for
subsequent /admin/api calls. This avoids hand-pasting the raw token into the UI.
The MVP is single shared-token; the team phase replaces this with Entra ID + RBAC.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from ..config import get_settings
from ..db import pool
from ..security import verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(body: LoginIn) -> dict:
    settings = get_settings()
    row = await pool().fetchrow(
        "SELECT username, password_hash, display_name, role FROM admin_users WHERE username = $1",
        body.username.strip().lower(),
    )
    # Always run a verify (even on missing user) to blunt username enumeration timing.
    stored = row["password_hash"] if row else "pbkdf2_sha256$200000$00$00"
    ok = verify_password(body.password, stored)
    if not row or not ok:
        await asyncio.sleep(0.4)  # light brute-force throttle
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid username or password")

    if not settings.api_token:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "API_TOKEN not configured on server")

    await pool().execute(
        "UPDATE admin_users SET last_login_at = now() WHERE username = $1", row["username"]
    )
    return {
        "token": settings.api_token,
        "user": {"username": row["username"], "name": row["display_name"], "role": row["role"]},
    }
