"""Public pipeline contract with a real model (Member 1, A-G3): load/reload/status, 503 behaviour, thresholds.
Needs pydantic (the schemas); skipped where it is not installed. Run: PYTHONPATH=backend pytest ml/tests -q"""
import json

import pytest

pytest.importorskip("pydantic")
pytest.importorskip("pandas")

from app.ml import model_store as S  # noqa: E402
from app.ml import pipeline  # noqa: E402
from app.schemas.ml_schemas import ListingInput, MlResult  # noqa: E402
from test_model_store import _edit_meta, _good_dir  # noqa: E402

LISTING = dict(title="Data Entry Intern", company_name="Brightpath Careers",
               description="Work from home. Pay registration fee of Rs 1499 to confirm your seat today.",
               contact_email="Brightpath.HR@Gmail.com", upfront_fee_amount=1499, application_channel="whatsapp")


@pytest.fixture()
def good(tmp_path, monkeypatch):
    d = _good_dir(tmp_path)
    monkeypatch.setattr(S, "ARTIFACT_DIR", d)
    pipeline._reset_for_tests()
    yield d
    pipeline._reset_for_tests()


@pytest.fixture()
def empty(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "ARTIFACT_DIR", tmp_path)
    pipeline._reset_for_tests()
    yield tmp_path
    pipeline._reset_for_tests()


def test_without_artifacts_nothing_is_faked(empty):
    pipeline.load_model()  # never raises
    st = pipeline.model_status()
    assert st["loaded"] is False and st["model_version"] is None and st["trained_at"] is None
    assert pipeline.get_model_info() is None and pipeline.get_metrics() is None and pipeline.get_load_error()
    with pytest.raises(pipeline.ModelNotLoadedError):
        pipeline.assess_listing(ListingInput(**LISTING))
    with pytest.raises(pipeline.ModelNotLoadedError):
        pipeline.predict_listing(ListingInput(**LISTING))
    with pytest.raises(pipeline.ModelNotLoadedError):
        pipeline.reload_model()


def test_loaded_model_status_and_real_result(good):
    pipeline.load_model()
    st = pipeline.model_status()
    assert set(st) == {"loaded", "model_version", "trained_at", "sklearn_version", "llm_enabled"}
    assert st["loaded"] is True and st["model_version"] == "proofhire-lr-1.0.0"
    r = pipeline.assess_listing(ListingInput(**LISTING), with_llm=False)
    MlResult.model_validate(r.model_dump())
    assert r.model_version == "proofhire-lr-1.0.0" and r.thresholds.low == 0.35 and r.thresholds.high == 0.70
    assert r.risk_score == round(r.risk_score, 4)
    assert r.evidence == [] and r.checklist == []  # interim until A-G4, never fabricated
    assert [e.value for e in r.entities] == ["brightpath.hr@gmail.com"]


def test_predict_listing_is_score_only(good, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("predict must not build entities/evidence")

    monkeypatch.setattr(pipeline, "interim_entities", boom)
    p = pipeline.predict_listing(ListingInput(**LISTING))
    assert set(p) == {"risk_score", "risk_level", "thresholds", "model_version"}


def test_risk_level_uses_thresholds_from_meta(good):
    _edit_meta(good, thresholds={"low": 0.0001, "high": 0.0002})
    pipeline.load_model()
    assert pipeline.assess_listing(ListingInput(**LISTING)).risk_level.value == "high"
    _edit_meta(good, thresholds={"low": 0.9998, "high": 0.9999})
    pipeline.reload_model()
    assert pipeline.assess_listing(ListingInput(**LISTING)).risk_level.value == "low"


def test_failed_reload_keeps_previous_model(good):
    pipeline.load_model()
    before = pipeline.assess_listing(ListingInput(**LISTING)).risk_score
    with open(good / S.MODEL_FILENAME, "ab") as fh:
        fh.write(b"corrupt")
    with pytest.raises(pipeline.ModelNotLoadedError):
        pipeline.reload_model()
    assert pipeline.model_status()["loaded"] is True  # old model kept
    assert pipeline.assess_listing(ListingInput(**LISTING)).risk_score == before


def test_reload_returns_meta_with_hash(good):
    pipeline.load_model()
    meta = pipeline.reload_model()
    assert meta["sha256_model"] == S.sha256_file(good / S.MODEL_FILENAME)
    assert meta["model_version"] == json.loads((good / S.META_FILENAME).read_text())["model_version"]


def test_sklearn_mismatch_reports_not_loaded(good):
    _edit_meta(good, sklearn_version="0.0.1")
    pipeline.load_model()
    assert pipeline.model_status()["loaded"] is False and "scikit-learn mismatch" in pipeline.get_load_error()
    with pytest.raises(pipeline.ModelNotLoadedError):
        pipeline.assess_listing(ListingInput(**LISTING))
