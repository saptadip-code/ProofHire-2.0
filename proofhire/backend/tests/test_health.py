"""Startup, /api/v1/health, /docs, CORS and the 5.5 error shape on unknown routes."""

from __future__ import annotations

import sys

import pytest
from fastapi.testclient import TestClient

from app import main
from app.db.init_db import DatabaseInitError
from app.routers import health as health_router


def _patch_health(monkeypatch, *, db_ok: bool, ml: dict):
    monkeypatch.setattr(health_router, "check_db", lambda: (db_ok, None if db_ok else "OperationalError (MySQL error 2003)"))
    monkeypatch.setattr(health_router, "_ml_status", lambda: ml)


def test_app_imports_and_has_expected_title():
    assert main.app.title == "ProofHire API"


def test_health_path_is_under_api_v1_only(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/health" in paths
    assert "/health" not in paths


def test_health_ok_when_db_and_model_are_up(client, monkeypatch):
    _patch_health(monkeypatch, db_ok=True, ml={"loaded": True, "model_version": "proofhire-lr-1.0.0", "llm_enabled": True})
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {
        "status": "ok",
        "db": True,
        "model_loaded": True,
        "model_version": "proofhire-lr-1.0.0",
        "llm_enabled": True,
        "version": "1.0.0",
    }
    assert r.headers["cache-control"] == "no-store"


def test_health_degraded_when_database_is_down(client, monkeypatch):
    _patch_health(monkeypatch, db_ok=False, ml={"loaded": True, "model_version": "x", "llm_enabled": False})
    r = client.get("/api/v1/health")
    assert r.status_code == 200  # B4: 200 even if degraded
    body = r.json()
    assert body["status"] == "degraded"
    assert body["db"] is False


def test_health_degraded_when_model_missing(client, monkeypatch):
    _patch_health(monkeypatch, db_ok=True, ml={})
    body = client.get("/api/v1/health").json()
    assert body["status"] == "degraded"
    assert body["db"] is True
    assert body["model_loaded"] is False
    assert body["model_version"] is None
    assert body["llm_enabled"] is False


def test_health_never_raises_when_ml_package_is_absent(client, monkeypatch):
    monkeypatch.setattr(health_router, "check_db", lambda: (True, None))
    # The ML package now exists, so simulate its absence: a None entry in sys.modules makes
    # `from app.ml.pipeline import model_status` raise ImportError (the case this test is about).
    monkeypatch.setitem(sys.modules, "app.ml.pipeline", None)
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["model_loaded"] is False


def test_docs_and_openapi_load(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_unknown_route_uses_section_5_5_error_shape(client):
    r = client.get("/api/v1/does-not-exist")
    assert r.status_code == 404
    assert r.json() == {"error": {"code": "not_found", "message": "Not found", "fields": []}}


def test_startup_survives_database_failure(monkeypatch):
    def boom():
        raise DatabaseInitError("Could not initialise the database at mysql+pymysql://u:***@h/db: OperationalError (MySQL error 2003)")

    monkeypatch.setattr(main, "init_db", boom)
    monkeypatch.setattr(health_router, "check_db", lambda: (False, "OperationalError (MySQL error 2003)"))
    with TestClient(main.app) as c:  # lifespan must not crash
        body = c.get("/api/v1/health").json()
    assert body["db"] is False
    assert body["status"] == "degraded"


def test_startup_calls_init_db_once(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "init_db", lambda: calls.append(1) or ())
    with TestClient(main.app):
        pass
    assert calls == [1]


def test_cors_allows_configured_origin_only(client):
    ok = client.options(
        "/api/v1/health",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"

    bad = client.options(
        "/api/v1/health",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in bad.headers
