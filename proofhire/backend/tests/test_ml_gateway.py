"""The integration boundary to Member 1's ML package (app/services/ml_gateway.py).

The real ML files are NOT delivered yet. These tests use TEST-ONLY fakes
(tests/ml_fakes.py) and prove that:
  * a missing / unloaded / incomplete ML package gives 503 model_unavailable
  * the pipeline is called through the agreed interface and its answer is validated
  * a crash or a wrong-shaped answer becomes a generic 500 with nothing leaked
"""

from __future__ import annotations

import sys
import types

import pytest

from app.core.errors import AppError
from app.schemas.assessment import ListingInput
from app.services import ml_gateway
from tests.ml_fakes import FakeMlListingInput, install_fake_ml, remove_ml, stub_result

LISTING = ListingInput(
    title="Data Entry Intern",
    company_name="Nexora Labs",
    description="Enter data into our internal tools for twenty hours per week.",
    contact_email="hr@nexoralabs.example",
)


def test_run_assessment_returns_the_validated_ml_output(monkeypatch):
    state = install_fake_ml(monkeypatch)
    out = ml_gateway.run_assessment(LISTING)
    assert isinstance(out, ml_gateway.MlOutput)
    assert out.risk_score == 0.12 and out.risk_level == "low"
    assert out.thresholds.low == 0.35 and out.thresholds.high == 0.7
    assert [e.id for e in out.evidence] == ["E1", "E2"]
    assert out.llm_meta.provider == "template"
    assert len(state.calls) == 1 and state.status_calls == 1


def test_fields_the_backend_does_not_know_are_ignored(monkeypatch):
    def richer(listing):
        result = stub_result(listing)
        result["new_field_from_member_1"] = {"anything": True}
        result["evidence"][0]["extra"] = 1
        return result

    install_fake_ml(monkeypatch, result_fn=richer)
    assert ml_gateway.run_assessment(LISTING).risk_level == "low"


def test_absent_ml_package_is_503(monkeypatch):
    remove_ml(monkeypatch)
    with pytest.raises(AppError) as info:
        ml_gateway.run_assessment(LISTING)
    assert info.value.status == 503 and info.value.code == "model_unavailable"


def test_unloaded_model_is_503_and_the_pipeline_is_not_called(monkeypatch):
    state = install_fake_ml(monkeypatch, loaded=False)
    with pytest.raises(AppError) as info:
        ml_gateway.run_assessment(LISTING)
    assert info.value.status == 503
    assert state.calls == []


def test_pipeline_without_assess_listing_is_503(monkeypatch):
    install_fake_ml(monkeypatch)
    del sys.modules["app.ml.pipeline"].assess_listing
    with pytest.raises(AppError) as info:
        ml_gateway.run_assessment(LISTING)
    assert info.value.status == 503


def test_missing_ml_listing_class_is_503(monkeypatch):
    install_fake_ml(monkeypatch)
    sys.modules["app.schemas.ml_schemas"] = types.ModuleType("app.schemas.ml_schemas")  # no ListingInput
    with pytest.raises(AppError) as info:
        ml_gateway.run_assessment(LISTING)
    assert info.value.status == 503


def test_model_status_that_raises_is_503(monkeypatch):
    install_fake_ml(monkeypatch)

    def broken():
        raise RuntimeError("boom")

    sys.modules["app.ml.pipeline"].model_status = broken
    with pytest.raises(AppError) as info:
        ml_gateway.run_assessment(LISTING)
    assert info.value.status == 503


def test_pipeline_without_model_status_is_still_called(monkeypatch):
    state = install_fake_ml(monkeypatch)
    del sys.modules["app.ml.pipeline"].model_status
    assert ml_gateway.run_assessment(LISTING).risk_level == "low"
    assert len(state.calls) == 1


def test_pipeline_exception_becomes_a_generic_500(monkeypatch):
    install_fake_ml(monkeypatch, raises=ValueError("contains the listing text"))
    with pytest.raises(AppError) as info:
        ml_gateway.run_assessment(LISTING)
    assert info.value.status == 500 and info.value.code == "internal_error"
    assert "listing text" not in info.value.message


def test_wrong_shaped_answer_becomes_a_generic_500(monkeypatch):
    install_fake_ml(monkeypatch, result_fn=lambda listing: {"risk_score": "high"})
    with pytest.raises(AppError) as info:
        ml_gateway.run_assessment(LISTING)
    assert info.value.status == 500


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r.update(risk_score=1.5),
        lambda r: r.update(risk_level="extreme"),
        lambda r: r["evidence"][0].update(severity=9),
        lambda r: r["evidence"][0].update(type="guess"),
        lambda r: r["explanation"].update(source="human"),
        lambda r: r["entities"].append({"type": "fax", "value": "1"}),
        lambda r: r["checklist"][0].update(priority=0),
    ],
)
def test_values_outside_the_documented_enums_and_ranges_are_rejected(monkeypatch, mutate):
    def bad(listing):
        result = stub_result(listing)
        mutate(result)
        return result

    install_fake_ml(monkeypatch, result_fn=bad)
    with pytest.raises(AppError) as info:
        ml_gateway.run_assessment(LISTING)
    assert info.value.status == 500


def test_the_ml_class_receives_the_backend_listing_as_data(monkeypatch):
    state = install_fake_ml(monkeypatch)
    ml_gateway.run_assessment(LISTING)
    assert state.calls[0]["contact_email"] == "hr@nexoralabs.example"
    assert FakeMlListingInput.model_validate(state.calls[0]).title == "Data Entry Intern"
