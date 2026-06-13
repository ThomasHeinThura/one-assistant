"""Qdrant RAG adapter.

Each vector carries source_id + content_hash so the verifier can detect drift
and re-embed (docs/07-datastore.md, Check 2).

Tier-1 note: confidential content must be embedded with an ON-DEVICE / self-hosted
model, never a cloud embedding API. `embed()` enforces this: Tier-1 may only use a
local backend, and the call fails closed if `cloud_embeddings` would be used.
"""
from __future__ import annotations

import hashlib
import logging

import httpx

from ..config import Settings

log = logging.getLogger("maria.qdrant")


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

    async def ensure_collection(self) -> None:
        """Create the collection if absent (idempotent)."""
        try:
            async with self._client() as client:
                await client.put(
                    f"/collections/{self.settings.qdrant_collection}",
                    json={"vectors": {"size": self.settings.embedding_dim, "distance": "Cosine"}},
                )
        except Exception as exc:
            log.warning("ensure_collection skipped: %s", exc)

    async def embed(self, text: str, *, tier: int) -> list[float]:
        """Return an embedding using the tier-appropriate backend.

        Tier 1 → on-device/self-hosted only. We refuse a cloud embedding for
        Tier-1 (fail closed). The real embedding model is wired in M2; until then
        this returns an empty vector and the caller skips the upsert.
        """
        if tier == 1 and self.settings.cloud_embeddings:
            raise PermissionError("Tier-1 content must not use cloud embeddings")
        # TODO(M2): call the self-hosted/on-device embedding model. Skeleton: no vector.
        return []

    async def upsert(self, *, source_id: str, text: str, tier: int, payload: dict) -> bool:
        """Embed + upsert one record. Returns True if a vector was written.

        Skeleton-safe: if no embedding backend is wired yet, logs and skips so the
        bus pipeline still runs green end-to-end.
        """
        try:
            vector = await self.embed(text, tier=tier)
        except PermissionError as exc:
            log.warning("refusing tier-1 cloud embed for %s: %s", source_id, exc)
            return False
        if not vector:
            log.info("reindex skipped (embedding backend wired in M2): %s", source_id)
            return False
        async with self._client() as client:
            await client.put(
                f"/collections/{self.settings.qdrant_collection}/points",
                json={"points": [{
                    "id": source_id,
                    "vector": vector,
                    "payload": {**payload, "content_hash": content_hash(text), "tier": tier},
                }]},
            )
        return True
