"""OpenRouter client — Tier 2/3 only, fail-closed on logging.

Every request carries provider.data_collection="deny". If no no-logging endpoint
is available the request errors and the caller falls back to on-device drafting
(docs/03-tech-stack.md). Tier-1 never reaches this module — see security.assert_cloud_allowed.
"""
from __future__ import annotations

import asyncio

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


async def complete(
    settings: Settings,
    messages: list[dict],
    *,
    api_key: str | None = None,
    max_tokens: int = 700,
    title: str = "Maria One",
) -> str:
    """Chat completion over the pinned no-logging model chain (Tier 2/3 only).

    Tries each pinned model in order; raises OpenRouterError if all fail so the
    caller can fall back to a deterministic answer. Enforces data_collection=deny.
    """
    key = api_key or settings.openrouter_api_key
    if not key:
        raise OpenRouterError("OPENROUTER_API_KEY not configured")
    headers = {"Authorization": f"Bearer {key}", "X-Title": title, "Content-Type": "application/json"}
    last_err = ""
    rate_limited = False
    async with httpx.AsyncClient(base_url=settings.openrouter_base_url, timeout=45) as client:
        # Two passes: free models are throttled upstream and ask us to "retry shortly".
        for attempt in range(2):
            for model in settings.openrouter_models:
                body = {
                    "model": model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "provider": {"data_collection": "deny"},  # fail closed: no logging/training
                }
                try:
                    resp = await client.post("/chat/completions", headers=headers, json=body)
                except Exception as exc:
                    last_err = f"unreachable: {str(exc)[:100]}"
                    continue
                txt = resp.text
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("choices"):
                        return data["choices"][0]["message"]["content"].strip()
                    last_err = f"empty: {txt[:120]}"
                # OpenRouter wraps upstream throttling as 429, or 400/200 with code 429.
                if resp.status_code == 429 or '"code":429' in txt or "rate-limit" in txt.lower():
                    rate_limited = True
                    last_err = "rate-limited upstream"
                else:
                    last_err = f"HTTP {resp.status_code}: {txt[:120]}"
            if rate_limited and attempt == 0:
                await asyncio.sleep(2.0)  # brief backoff, then one more pass
                continue
            break
    prefix = "rate_limited: " if rate_limited else ""
    raise OpenRouterError(f"{prefix}all pinned no-logging models failed: {last_err}")


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
