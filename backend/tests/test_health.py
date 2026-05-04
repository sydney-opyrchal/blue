"""Smoke tests for the /health endpoint — SPEC NFR-5."""
from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    # Import lazily so we can patch module state before the app constructs.
    from app import main as main_module
    importlib.reload(main_module)
    # Force the dependency-status booleans to a known value without standing
    # up a real broker or DB.
    main_module._mqtt_connected = True
    return TestClient(main_module.app), main_module


def test_health_returns_envelope_shape(client):
    c, _ = client
    r = c.get("/health")
    body = r.json()
    assert set(body.keys()) >= {"status", "service", "version", "timestamp", "dependencies"}
    assert body["service"] == "ingest"
    assert "mqtt" in body["dependencies"]
    assert "database" in body["dependencies"]


def test_health_returns_503_when_all_deps_unhealthy(client):
    c, m = client
    m._mqtt_connected = False
    m.db_pool = None
    r = c.get("/health")
    assert r.status_code == 503
    assert r.json()["status"] == "unhealthy"
