"""Bearer-token auth + the Tier-1 cloud guard (defense in depth).

MVP is single-user, so a single rotating API token authenticates the mobile app.
The team phase replaces this with Microsoft Entra ID (PKCE) + RBAC.
"""
from __future__ import annotations

import hashlib
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings, get_settings

_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str, *, iterations: int = 200_000) -> str:
    """pbkdf2-sha256 hash, stdlib only (no bcrypt dependency)."""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time verify against a pbkdf2_sha256$iter$salt$hash string."""
    try:
        scheme, iters, salt_hex, hash_hex = stored.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iters))
        return secrets.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


async def require_auth(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> None:
    # In dev with no token configured, allow through so `docker compose up` is
    # usable immediately. Staging/prod MUST set API_TOKEN.
    if not settings.api_token:
        if settings.is_prod:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "API_TOKEN not configured")
        return
    if creds is None or not secrets.compare_digest(creds.credentials, settings.api_token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or missing bearer token")


def assert_cloud_allowed(sensitivity_tier: int) -> None:
    """No-op since the on-device path was removed (all AI now runs on Ollama Cloud).

    Previously Tier-1 (confidential) was blocked from the cloud and drafted on-device.
    The app is now a thin cloud client with no on-device model, so every tier is
    processed by Ollama Cloud (no-logging, no-training). Sensitivity tiers are kept as
    advisory labels for classification/audit, not as a data-residency guarantee.
    Kept as a stable seam: re-introduce a guard here if a confidential path returns.
    """
    return None
