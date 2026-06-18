"""Ollama Cloud client — Tier 2/3 only.

Talks to Ollama's OpenAI-compatible endpoint (https://ollama.com/v1) with a Bearer
API key. Ollama's cloud does not retain or train on prompts. This is the project's
only AI engine — the on-device/SLM path was removed, so every tier is drafted here
(sensitivity tiers are advisory labels now; see security.assert_cloud_allowed).

On the paid ("Pro") plan, gemma4:31b and additional models are available behind one key
and free-tier rate caps no longer apply. If a cap is ever hit the caller still falls back
to a deterministic answer.
"""
from __future__ import annotations

import asyncio

import httpx

from ..config import Settings
from .langfuse_client import trace


class OllamaError(RuntimeError):
    pass


def _rate_limited(status_code: int, text: str) -> bool:
    """Ollama returns 429 on free-tier caps; some upstreams wrap it in the body."""
    return status_code == 429 or '"code":429' in text or "rate limit" in text.lower()


def _needs_subscription(text: str) -> bool:
    return "subscription" in text.lower() or "upgrade for access" in text.lower()


async def ping_model(settings: Settings, model: str, api_key: str | None = None) -> tuple[bool, str]:
    """Minimal completion to verify a model is reachable + responsive.

    Returns (ok, detail).
    """
    key = api_key or settings.ollama_api_key
    if not key:
        return False, "no Ollama API key"
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
        "max_tokens": 5,
    }
    try:
        async with httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=30) as client:
            resp = await client.post("/chat/completions",
                                     headers={"Authorization": f"Bearer {key}"}, json=body)
        txt = resp.text
        if resp.status_code == 200 and not _needs_subscription(txt):
            data = resp.json()
            if data.get("choices"):
                content = data["choices"][0]["message"]["content"].strip()
                return True, f"responsive (“{content[:24]}”)"
            return False, f"empty response: {txt[:80]}"
        if _needs_subscription(txt):
            return False, "requires a paid Ollama subscription"
        if _rate_limited(resp.status_code, txt):
            # Valid model + key, just throttled on the free tier — counts as available.
            return True, "available (free-tier rate limit)"
        if resp.status_code in (401, 403):
            return False, "API key rejected"
        if resp.status_code == 404:
            return False, "model not available on Ollama Cloud"
        return False, f"HTTP {resp.status_code}: {txt[:80]}"
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
    """Chat completion over the pinned model chain (Tier 2/3 only).

    Tries each pinned model in order; raises OllamaError if all fail so the caller
    can fall back to a deterministic answer.
    """
    key = api_key or settings.ollama_api_key
    if not key:
        raise OllamaError("OLLAMA_API_KEY not configured")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    last_err = ""
    rate_limited = False
    async with httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=60) as client:
        # Two passes: free-tier caps ask us to retry shortly.
        for attempt in range(2):
            for model in settings.ollama_models:
                body = {"model": model, "messages": messages, "max_tokens": max_tokens}
                try:
                    resp = await client.post("/chat/completions", headers=headers, json=body)
                except Exception as exc:
                    last_err = f"unreachable: {str(exc)[:100]}"
                    continue
                txt = resp.text
                if resp.status_code == 200 and not _needs_subscription(txt):
                    data = resp.json()
                    if data.get("choices"):
                        return data["choices"][0]["message"]["content"].strip()
                    last_err = f"empty: {txt[:120]}"
                elif _needs_subscription(txt):
                    last_err = f"{model} requires a paid subscription"
                elif _rate_limited(resp.status_code, txt):
                    rate_limited = True
                    last_err = "rate-limited (free-tier cap)"
                else:
                    last_err = f"HTTP {resp.status_code}: {txt[:120]}"
            if rate_limited and attempt == 0:
                await asyncio.sleep(2.0)  # brief backoff, then one more pass
                continue
            break
    prefix = "rate_limited: " if rate_limited else ""
    raise OllamaError(f"{prefix}all pinned models failed: {last_err}")


async def draft_mom(settings: Settings, prompt: str, *, title: str = "Maria One", tier: int = 2) -> str:
    if not settings.ollama_api_key:
        raise OllamaError("OLLAMA_API_KEY not configured")

    headers = {
        "Authorization": f"Bearer {settings.ollama_api_key}",
        "Content-Type": "application/json",
    }
    last_err: Exception | None = None
    with trace("mom_draft_cloud", metadata={"tier": tier}) as span:
        async with httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=90) as client:
            for model in settings.ollama_models:  # pinned chain
                body = {"model": model, "messages": [{"role": "user", "content": prompt}]}
                try:
                    resp = await client.post("/chat/completions", headers=headers, json=body)
                    resp.raise_for_status()
                    data = resp.json()
                    usage = data.get("usage", {})
                    span.event("ollama.completion", {"model": model, "usage": usage})
                    return data["choices"][0]["message"]["content"]
                except Exception as exc:  # try next pinned model, else bubble up
                    last_err = exc
                    span.event("ollama.error", {"model": model, "error": str(exc)[:120]})
                    continue
    raise OllamaError(f"all pinned models failed: {last_err}")
