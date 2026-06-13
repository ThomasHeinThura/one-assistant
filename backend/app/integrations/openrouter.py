"""OpenRouter client — Tier 2/3 only, fail-closed on logging.

Every request carries provider.data_collection="deny". If no no-logging endpoint
is available the request errors and the caller falls back to on-device drafting
(docs/03-tech-stack.md). Tier-1 never reaches this module — see security.assert_cloud_allowed.
"""
from __future__ import annotations

import httpx

from ..config import Settings
from .langfuse_client import trace


class OpenRouterError(RuntimeError):
    pass


async def ping_model(settings: Settings, model: str, api_key: str | None = None) -> tuple[bool, str]:
    """Minimal completion to verify a model is reachable + responsive.

    Returns (ok, detail). Enforces data_collection: deny like all calls.
    """
    key = api_key or settings.openrouter_api_key
    if not key:
        return False, "no OpenRouter API key"
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
        "max_tokens": 5,
        "provider": {"data_collection": "deny"},
    }
    try:
        async with httpx.AsyncClient(base_url=settings.openrouter_base_url, timeout=20) as client:
            resp = await client.post("/chat/completions",
                                     headers={"Authorization": f"Bearer {key}"}, json=body)
        if resp.status_code == 200:
            txt = resp.json()["choices"][0]["message"]["content"].strip()
            return True, f"responsive (“{txt[:24]}”)"
        if resp.status_code == 429:
            # Valid model + key, just throttled on the free tier — counts as available.
            return True, "available (free-tier rate limit)"
        if resp.status_code in (401, 403):
            return False, "API key rejected"
        if resp.status_code == 404:
            return False, "model not available on OpenRouter"
        if resp.status_code == 400 and "not a valid model" in resp.text:
            return False, "invalid model ID"
        return False, f"HTTP {resp.status_code}: {resp.text[:80]}"
    except Exception as exc:
        return False, f"unreachable: {str(exc)[:80]}"


async def draft_mom(settings: Settings, prompt: str, *, title: str = "Maria One", tier: int = 2) -> str:
    if not settings.openrouter_api_key:
        raise OpenRouterError("OPENROUTER_API_KEY not configured")

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "X-Title": title,
        "Content-Type": "application/json",
    }
    last_err: Exception | None = None
    with trace("mom_draft_cloud", metadata={"tier": tier}) as span:
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
                    usage = data.get("usage", {})
                    span.event("openrouter.completion", {"model": model, "usage": usage})
                    return data["choices"][0]["message"]["content"]
                except Exception as exc:  # try next pinned model, else bubble up
                    last_err = exc
                    span.event("openrouter.error", {"model": model, "error": str(exc)[:120]})
                    continue
    raise OpenRouterError(f"all pinned no-logging models failed: {last_err}")
