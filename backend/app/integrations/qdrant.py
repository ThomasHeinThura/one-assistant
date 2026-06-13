"""Qdrant RAG adapter.

Each vector carries source_id + content_hash so the verifier can detect drift
and re-embed (docs/07-datastore.md, Check 2).

Tier-1 note: confidential content must be embedded with an ON-DEVICE / self-hosted
model, never a cloud embedding API. The embed() seam here is where that routing
lives — `tier` is passed through so the wrong backend can never be selected.
"""
from __future__ import annotations

import hashlib

import httpx

from ..config import Settings


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class QdrantAdapter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.settings.qdrant_url, timeout=15)

    async def healthy(self) -> bool:
        try:
            async with self._client() as client:
                resp = await client.get("/readyz")
                return resp.status_code == 200
        except Exception:
            return False

    async def embed(self, text: str, *, tier: int) -> list[float]:
        """Return an embedding using the tier-appropriate backend.

        TODO: tier==1 -> on-device/self-hosted embedding only; tier 2/3 may use a
        cloud embedding endpoint with no-logging enforced. Stubbed for skeleton.
        """
        raise NotImplementedError("embedding backend wired in M2")

    async def upsert(self, *, source_id: str, text: str, tier: int, payload: dict) -> None:
        raise NotImplementedError("vector upsert wired in M2")
