"""ML API tests (Member 1). Run from repo root: PYTHONPATH=backend pytest backend/tests/test_ml_api.py -q

A-G3: /predict serves the REAL model. Tests that need a loaded model use `loaded_client`, which skips (with the
loader's reason) when the committed artifact cannot load in the current environment - e.g. it was trained with a
different scikit-learn than the one running. Tests for the "no model" behaviour point the loader at an empty dir.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ml import model_store, pipeline
from app.routers import ml

PREFIX = "/api/v1/ml"
GOOD = {
    "title": "Data Entry Intern",
    "company_name": "Brightpath Careers",
    "description": "Work from home. Pay registration fee to confirm your seat today.",
    "contact_email": "Brightpath.HR@Gmail.com",
    "upfront_fee_amount": 1499,
}
EXPECTED_ROUTES = {
    ("GET", "/health"), ("GET", "/model-info"), ("GET", "/metrics"),
    ("POST", "/predict"), ("POST", "/evidence"), ("POST", "/explain"),
    ("POST", "/extract-entities"), ("POST", "/reload"),
}


def _make_client(monkeypatch):
    monkeypatch.delenv("INTERNAL_API_KEY", raising=False)
    pipeline._reset_for_tests()
    app = FastAPI()
    app.include_router(ml.router, prefix=PREFIX)  # same call main.py must make
    return TestClient(app)


@pytest.fixture()
def client(monkeypatch):
    yield _make_client(monkeypatch)
    pipeline._reset_for_tests()


@pytest.fixture()
def loaded_client(monkeypatch):
    c = _make_client(monkeypatch)
    pipeline.load_model()
    if not pipeline.model_status()["loaded"]:
        pytest.skip(f"committed artifact cannot load here: {pipeline.get_load_error()}")
    yield c
    pipeline._reset_for_tests()


@pytest.fixture()
def unloaded_client(monkeypatch, tmp_path):
    c = _make_client(monkeypatch)
    monkeypatch.setattr(model_store, "ARTIFACT_DIR", tmp_path)  # empty dir: nothing to load
    yield c
    pipeline._reset_for_tests()


def test_route_registration_exact_paths_and_methods(client):
    found = set()
    for path, ops in client.get("/openapi.json").json()["paths"].items():
        if path.startswith(PREFIX):
            for method in ops:
                found.add((method.upper(), path[len(PREFIX):]))
    assert found == EXPECTED_ROUTES


def test_health_shape_and_loaded_flag_match_loader(client):
    r = client.get(f"{PREFIX}/health")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"loaded", "model_version", "trained_at", "sklearn_version",
                         "llm_enabled", "llm_circuit_open"}
    assert body["loaded"] is (pipeline.get_model_info() is not None)


def test_health_reports_not_loaded_without_artifacts(unloaded_client):
    body = unloaded_client.get(f"{PREFIX}/health").json()
    assert body["loaded"] is False and body["model_version"] is None and body["trained_at"] is None


def test_model_info_and_metrics_503_without_artifacts(unloaded_client):
    for path in ("model-info", "metrics"):
        r = unloaded_client.get(f"{PREFIX}/{path}")
        assert r.status_code == 503
        assert r.json()["error"]["code"] == "model_unavailable"


def test_predict_evidence_explain_503_without_artifacts(unloaded_client):
    for path in ("predict", "evidence", "explain"):
        r = unloaded_client.post(f"{PREFIX}/{path}", json=GOOD)
        assert r.status_code == 503
        assert r.json()["error"]["code"] == "model_unavailable"


def test_model_info_and_metrics_cache_headers_and_etag(loaded_client):
    info = loaded_client.get(f"{PREFIX}/model-info")
    assert info.status_code == 200
    assert info.headers["cache-control"] == "public, max-age=300"
    assert info.headers["etag"] == f'"{info.json()["sha256_model"]}"'
    again = loaded_client.get(f"{PREFIX}/model-info", headers={"If-None-Match": info.headers["etag"]})
    assert again.status_code == 304
    met = loaded_client.get(f"{PREFIX}/metrics")
    assert met.status_code == 200
    assert met.headers["cache-control"] == "public, max-age=300" and met.headers["etag"]
    assert set(met.json()) == {"synthetic_test", "baselines", "pattern_holdout", "handwritten", "cv", "limitations"}


def test_predict_is_real_score_only(loaded_client):
    p = loaded_client.post(f"{PREFIX}/predict", json=GOOD)
    assert p.status_code == 200
    body = p.json()
    assert set(body) == {"risk_score", "risk_level", "thresholds", "model_version"}
    assert 0.0 <= body["risk_score"] <= 1.0
    assert body["model_version"] == pipeline.get_model_info()["model_version"]
    assert body["thresholds"] == pipeline.get_model_info()["thresholds"]
    assert "X-ProofHire-Stub" not in p.headers  # the score is not a stub any more


def test_risky_listing_scores_above_corporate_listing(loaded_client):
    risky = dict(GOOD, application_channel="whatsapp", interview_mode="chat_only")
    clean = {
        "title": "Software Developer Intern", "company_name": "Nexora Labs",
        "description": "Join Nexora Labs and work with a mentor on our product. We run a structured interview and "
                       "give weekly feedback. Apply through the careers page on our official website.",
        "requirements": "Comfortable with Python and version control, interest in testing, clear written "
                        "communication and a willingness to learn from code review every week of the programme.",
        "contact_email": "careers@nexora.com", "company_website": "https://nexora.com",
        "application_channel": "email", "interview_mode": "video_call",
    }
    hi = loaded_client.post(f"{PREFIX}/predict", json=risky).json()["risk_score"]
    lo = loaded_client.post(f"{PREFIX}/predict", json=clean).json()["risk_score"]
    assert hi > lo


def test_evidence_explain_entities_interim_shapes(loaded_client):
    e = loaded_client.post(f"{PREFIX}/evidence", json=GOOD)
    assert set(e.json()) == {"risk_score", "risk_level", "evidence"}
    assert e.headers["X-ProofHire-Stub"] == "true"  # evidence content is still interim (A-G4)
    x = loaded_client.post(f"{PREFIX}/explain", json=GOOD).json()
    assert {"explanation", "checklist", "entities", "llm_meta"} <= set(x)
    assert x["explanation"]["source"] == "template"
    assert all("id" not in c for c in x["checklist"])


def test_extract_entities_needs_no_model(unloaded_client):
    ent = unloaded_client.post(f"{PREFIX}/extract-entities", json=GOOD)
    assert ent.status_code == 200
    assert ent.json() == {"entities": [{"type": "email", "value": "brightpath.hr@gmail.com"}]}


def test_reload_without_artifacts_fails_honestly(unloaded_client):
    r = unloaded_client.post(f"{PREFIX}/reload")
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "internal_error"


def test_reload_success_returns_meta_hash(loaded_client):
    r = loaded_client.post(f"{PREFIX}/reload")
    assert r.status_code == 200
    meta = pipeline.get_model_info()
    assert r.json() == {"reloaded": True, "model_version": meta["model_version"], "sha256": meta["sha256_model"]}


def test_invalid_input_returns_422(client):
    assert client.post(f"{PREFIX}/predict", json={"title": "x"}).status_code == 422


# ---- authentication (X-Internal-Key / INTERNAL_API_KEY)
POST_PATHS = ["predict", "evidence", "explain", "extract-entities"]


def test_auth_skipped_when_env_empty(loaded_client, monkeypatch):
    monkeypatch.setenv("INTERNAL_API_KEY", "")
    assert loaded_client.post(f"{PREFIX}/predict", json=GOOD).status_code == 200


@pytest.mark.parametrize("path", POST_PATHS + ["reload"])
def test_auth_rejects_missing_and_wrong_key(client, monkeypatch, path):
    monkeypatch.setenv("INTERNAL_API_KEY", "secret")
    body = None if path == "reload" else GOOD
    for headers in ({}, {"X-Internal-Key": "wrong"}):
        r = client.post(f"{PREFIX}/{path}", json=body, headers=headers)
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize("path", POST_PATHS)
def test_auth_accepts_correct_key(loaded_client, monkeypatch, path):
    monkeypatch.setenv("INTERNAL_API_KEY", "secret")
    r = loaded_client.post(f"{PREFIX}/{path}", json=GOOD, headers={"X-Internal-Key": "secret"})
    assert r.status_code == 200


def test_get_endpoints_need_no_key(client, monkeypatch):
    monkeypatch.setenv("INTERNAL_API_KEY", "secret")
    assert client.get(f"{PREFIX}/health").status_code == 200
