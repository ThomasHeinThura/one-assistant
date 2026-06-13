"""Smoke test: app imports and liveness works without any datastore.

Run: pip install pytest && pytest -q   (from backend/)

Note: we do NOT use `with TestClient(app)` here — the context manager runs the
lifespan (which opens the DB pool). /healthz touches no datastore, so a plain
client call exercises it without needing Postgres up.
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_healthz():
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_security_headers_present():
    resp = client.get("/healthz")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
