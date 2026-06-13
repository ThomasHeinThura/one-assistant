"""Plane adapter (REST, service-token auth — NOT interactive MCP).

Per the audit, Plane is the SOURCE OF TRUTH for ticket status:
  * outbound: we create a follow-up issue when a MoM action item is dispatched,
    using a dedup key so retries never double-create (idempotency).
  * inbound:  pull_changes() reads issues changed since a cursor and lets the
    derive/reindex path update the local mirror WITHOUT the verifier clobbering
    a teammate's Plane-side edit.

Methods are stubbed for the walking skeleton; wire the real Plane API in M4.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from ..config import Settings


@dataclass
class PlaneIssue:
    id: str
    title: str
    status: str


class PlaneAdapter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def configured(self) -> bool:
        return bool(self.settings.plane_api_key and self.settings.plane_base_url)

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.settings.plane_base_url,
            headers={"X-API-Key": self.settings.plane_api_key},
            timeout=30,
        )

    async def find_by_dedup_key(self, dedup_key: str) -> PlaneIssue | None:
        """Look up an existing issue carrying our dedup key (idempotency)."""
        if not self.configured:
            return None
        # TODO(M4): query Plane by an external_id / label == dedup_key.
        return None

    async def create_issue(self, *, title: str, description: str, dedup_key: str) -> PlaneIssue:
        """Idempotent create: reuse the issue if the dedup key already exists."""
        existing = await self.find_by_dedup_key(dedup_key)
        if existing:
            return existing
        if not self.configured:
            # Skeleton mode: deterministic fake id so dispatch state is exercisable.
            return PlaneIssue(id=f"PLANE-STUB-{dedup_key[:12]}", title=title, status="new")
        # TODO(M4): POST issue, attach dedup_key as external id/label, return real id.
        raise NotImplementedError("real Plane create lands in M4")

    async def pull_changes(self, since_cursor: str | None) -> list[PlaneIssue]:
        """Inbound sync source: issues changed in Plane since the cursor."""
        if not self.configured:
            return []
        # TODO(M4): GET issues updated_at > cursor (or consume Plane webhooks).
        return []
