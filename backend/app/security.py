"""Bearer-token auth + the Tier-1 cloud guard (defense in depth).

MVP is single-user, so a single rotating API token authenticates the mobile app.
The team phase replaces this with Microsoft Entra ID (PKCE) + RBAC.
"""
from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings, get_settings

_bearer = HTTPBearer(auto_error=False)


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
    """Backend re-check of the on-device tier decision (architecture §sensitivity).

    Tier 1 (confidential) must NEVER be sent to any cloud LLM. The phone decides
    first; this is the server-side fail-closed backstop.
    """
    if sensitivity_tier == 1:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Tier-1 (confidential) content cannot be processed in the cloud; draft on-device.",
        )
