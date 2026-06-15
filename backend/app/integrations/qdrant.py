"""Qdrant RAG adapter.

Each vector carries source_id + content_hash so the verifier can detect drift
and re-embed (docs/07-datastore.md, Check 2).

Tier-1 note: confidential content must be embedded with an ON-DEVICE / self-hosted
model, never a cloud embedding API. We use **fastembed** (ONNX, runs in-process —
no network, no cloud) as the self-hosted backend, so Tier-2/3 RAG works offline.
`embed()` still fails closed if a cloud embedding backend were ever enabled for
Tier-1 content. Tier-1 confidential drafting stays on the phone and never reaches
this service at all.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging

import httpx

from ..config import Settings

log = logging.getLogger("maria.qdrant")

# Self-hosted embedding model. bge-base-en-v1.5 → 768-dim, matches embedding_dim.
# fastembed downloads the ONNX weights once on first use, then runs locally.
_EMBED_MODEL_NAME = "BAAI/bge-base-en-v1.5"
_embedder = None            # lazy singleton (loaded on first embed)
_embedder_lock = asyncio.Lock()
_embedder_failed = False    # if load fails once, stop retrying (stay skeleton-safe)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def _get_embedder():
    """Load the fastembed model once. Returns None if unavailable (fail-soft)."""
    global _embedder, _embedder_failed
    if _embedder is not None or _embedder_failed:
        return _embedder
    async with _embedder_lock:
        if _embedder is not None or _embedder_failed:
            return _embedder
        try:
            from fastembed import TextEmbedding  # heavy import — defer to first use

            # Model download + load is blocking; keep the event loop free.
            _embedder = await asyncio.to_thread(TextEmbedding, model_name=_EMBED_MODEL_NAME)
            log.info("fastembed loaded: %s", _EMBED_MODEL_NAME)
        except Exception as exc:  # not installed / no model / offline
            _embedder_failed = True
            log.warning("fastembed unavailable, RAG embedding disabled: %s", exc)
    return _embedder


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
        Tier-1 (fail closed). fastembed runs locally so it is always allowed;
        the guard only trips if a cloud backend is ever turned on for Tier-1.
        Returns [] (caller skips) if no local embedder is available.
        """
        if tier == 1 and self.settings.cloud_embeddings:
            raise PermissionError("Tier-1 content must not use cloud embeddings")
        text = (text or "").strip()
        if not text:
            return []
        embedder = await _get_embedder()
        if embedder is None:
            return []
        # fastembed.embed() is a generator over numpy arrays; run off-loop.
        vectors = await asyncio.to_thread(lambda: list(embedder.embed([text])))
        if not vectors:
            return []
        return [float(x) for x in vectors[0]]

    async def upsert(self, *, source_id: str, text: str, tier: int, payload: dict) -> bool:
        """Embed + upsert one record. Returns True if a vector was written.

        Fail-soft: if no embedding backend is available, logs and skips so the
        bus pipeline still runs green end-to-end.
        """
        try:
            vector = await self.embed(text, tier=tier)
        except PermissionError as exc:
            log.warning("refusing tier-1 cloud embed for %s: %s", source_id, exc)
            return False
        if not vector:
            log.info("reindex skipped (no local embedder yet): %s", source_id)
            return False
        async with self._client() as client:
            await client.put(
                f"/collections/{self.settings.qdrant_collection}/points",
                params={"wait": "true"},
                json={"points": [{
                    "id": _point_id(source_id),
                    "vector": vector,
                    "payload": {**payload, "source_id": source_id, "text": text[:2000],
                                "content_hash": content_hash(text), "tier": tier},
                }]},
            )
        return True

    async def search(self, query: str, *, limit: int = 4, tier: int = 2) -> list[dict]:
        """Retrieve the top-k most relevant indexed records for a query.

        Returns a list of {score, text, source_id, payload} dicts; empty if RAG
        is unavailable (no embedder / Qdrant down) so chat still answers.
        """
        try:
            vector = await self.embed(query, tier=tier)
            if not vector:
                return []
            async with self._client() as client:
                resp = await client.post(
                    f"/collections/{self.settings.qdrant_collection}/points/search",
                    json={"vector": vector, "limit": limit, "with_payload": True},
                )
                if resp.status_code != 200:
                    return []
                hits = resp.json().get("result", [])
        except Exception as exc:
            log.info("rag search skipped: %s", exc)
            return []
        out = []
        for h in hits:
            p = h.get("payload") or {}
            out.append({"score": h.get("score"), "text": p.get("text", ""),
                        "source_id": p.get("source_id"), "payload": p})
        return out


def _point_id(source_id: str) -> str:
    """Qdrant point IDs must be UUIDs or unsigned ints. Hash arbitrary source_id
    into a deterministic UUID5-style hex so re-indexing the same record overwrites."""
    import uuid

    return str(uuid.uuid5(uuid.NAMESPACE_URL, source_id))
