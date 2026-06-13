"""OpenRouter client — Tier 2/3 only, fail-closed on logging.

Every request carries provider.data_collection="deny". If no no-logging endpoint
is available the request errors and the caller falls back to on-device drafting
(docs/03-tech-stack.md). Tier-1 never reaches this module — see security.assert_cloud_allowed.
"""
from __future__ import annotations

import httpx

from ..config import Settings


class OpenRouterError(RuntimeError):
    pass


async def draft_mom(settings: Settings, prompt: str, *, title: str = "Maria One") -> str:
    if not settings.openrouter_api_key:
        raise OpenRouterError("OPENROUTER_API_KEY not configured")

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "X-Title": title,
        "Content-Type": "application/json",
    }
    last_err: Exception | None = None
    async with httpx.AsyncClient(base_url=settings.openrouter_base_url, timeout=60) as client:
        for model in settings.openrouter_models:  # pinned no-logging chain
            body = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                # Fail closed: refuse any endpoint that would log/train on the prompt.
                "provider": {"data_collection": "deny"},
            }
            try:
                resp = await client.post("/chat/completions", headers=headers, json=body)
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            except Exception as exc:  # try next pinned model, else bubble up
                last_err = exc
                continue
    raise OpenRouterError(f"all pinned no-logging models failed: {last_err}")
