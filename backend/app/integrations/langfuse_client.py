"""Langfuse (self-hosted) tracing wrapper.

One trace per business event (MoM draft, each dispatch call, chat) with tokens,
cost, latency, sensitivity tier and destination. Kept in-stack so confidential
prompts never reach a third-party observability SaaS.

Degrades to a no-op when keys are absent or the SDK isn't installed, so dev and
tests run without Langfuse configured.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager

from ..config import get_settings

log = logging.getLogger("maria.langfuse")

try:
    from langfuse import Langfuse  # type: ignore
except Exception:  # SDK not installed in this environment
    Langfuse = None  # type: ignore

_client = None
_initialised = False


def _get_client():
    global _client, _initialised
    if _initialised:
        return _client
    _initialised = True
    s = get_settings()
    if Langfuse is None or not (s.langfuse_public_key and s.langfuse_secret_key):
        log.info("Langfuse disabled (no SDK or keys); tracing is a no-op")
        _client = None
        return None
    _client = Langfuse(
        public_key=s.langfuse_public_key,
        secret_key=s.langfuse_secret_key,
        host=s.langfuse_host,
    )
    return _client


@contextmanager
def trace(name: str, *, metadata: dict | None = None):
    """Context manager that opens a Langfuse trace, or yields a no-op shim.

        with trace("mom_confirmed", metadata={"tier": 1}) as span:
            span.event("dispatch.plane", {"status": "done"})
    """
    client = _get_client()
    if client is None:
        yield _NoopSpan()
        return
    root = client.trace(name=name, metadata=metadata or {})
    try:
        yield _Span(root)
    finally:
        try:
            client.flush()
        except Exception:
            pass


class _Span:
    def __init__(self, node):
        self._node = node

    def event(self, name: str, payload: dict | None = None) -> None:
        try:
            self._node.event(name=name, metadata=payload or {})
        except Exception:
            pass


class _NoopSpan:
    def event(self, name: str, payload: dict | None = None) -> None:
        log.debug("trace event (noop): %s %s", name, payload)
