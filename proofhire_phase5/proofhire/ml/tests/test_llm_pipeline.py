"""assess_listing() with the LLM subsystem (Member 1, A-G5). Network free: llm_client._post_json is a scripted fake.
Needs the committed artifact to load (scikit-learn 1.7.2); otherwise the tests skip like the other pipeline tests.
"""
import json

import pytest

pytest.importorskip("pydantic")
pytest.importorskip("sklearn")

from app.ml import checklist as C  # noqa: E402
from app.ml import llm_client as LC  # noqa: E402
from app.ml import pipeline as P  # noqa: E402
from app.schemas.ml_schemas import ListingInput  # noqa: E402

RISKY = dict(
    title="Data Entry Intern", company_name="Brightpath Careers",
    description="Work from home. Pay registration fee of Rs 1,499 to confirm your seat. Send Aadhaar today. Apply now, limited seats!",
    contact_email="Brightpath.HR@Gmail.com", upfront_fee_amount=1499, application_channel="whatsapp",
    interview_mode="chat_only", salary_max=90000)
CLEAN = dict(
    title="Software Developer Intern", company_name="Nexora Technologies Pvt. Ltd.",
    description=("Join Nexora and work with a mentor on our product. We run a structured interview and give weekly "
                 "feedback to every intern. You will write and review code, fix bugs, document features and present "
                 "your work to the team every two weeks during the programme. Apply through our careers page."),
    requirements=("Comfortable with Python and version control, interest in testing, clear written communication and a "
                  "willingness to learn from code review every week of the programme."),
    contact_email="careers@nexora.com", contact_phone="+91 98765 43210", company_website="https://www.nexora.com",
    application_channel="email", interview_mode="video_call", salary_min=15000, salary_max=25000)
LIBRARY = [{"code": "CHK_NO_FEE", "text": "Never pay any fee before a signed offer.", "priority": 1, "triggers": ["UPFRONT_FEE"]},
           {"code": "CHK_GENERAL_RECRUITER", "text": "Find the recruiter on the official page.", "priority": 3, "triggers": ["*"]}]
GOOD = {"summary": "This listing shows signals that are often linked to fee-based job offers.",
        "key_concerns": [{"text": "A fee is requested.", "evidence_ids": ["E1"]}],
        "what_to_verify": ["Ask for a written offer."]}


class Http:
    def __init__(self):
        self.script, self.calls = [], []

    def __call__(self, url, api_key, body, timeout):
        self.calls.append(url)
        item = self.script.pop(0) if self.script else ("ok", GOOD)
        if item[0] == "timeout":
            raise LC._Timeout("t")
        if item[0] == "status":
            return item[1], ""
        return 200, json.dumps({"choices": [{"message": {"content": json.dumps(item[1])}}]})


@pytest.fixture()
def real(tmp_path, monkeypatch):
    lib = tmp_path / "checklist_library.json"
    lib.write_text(json.dumps(LIBRARY), encoding="utf-8")
    monkeypatch.setattr(C, "LIBRARY_PATH", lib)
    C.clear_cache()
    P._reset_for_tests()
    P.load_model()
    if not P.model_status()["loaded"]:
        pytest.skip(f"committed artifact cannot load here: {P.get_load_error()}")
    yield P
    P._reset_for_tests()
    C.clear_cache()


@pytest.fixture()
def http(monkeypatch):
    h = Http()
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_API_KEY", "test-key-not-real")
    monkeypatch.setattr(LC, "_post_json", h)
    LC.reset_state()
    return h


def L(**kw):
    return ListingInput(**kw)


def essentials(r):
    return (r.risk_score, r.risk_level.value, r.thresholds.model_dump(), r.model_version, [e.model_dump() for e in r.evidence],
            [c.model_dump() for c in r.checklist], [e.model_dump() for e in r.entities])


def test_works_with_every_key_removed(real):
    r = P.assess_listing(L(**RISKY))  # conftest removed all LLM_* variables
    assert r.explanation.source.value == "template" and r.llm_meta.provider == "template" and r.llm_meta.success is True
    assert r.risk_score > 0 and r.evidence and r.explanation.what_to_verify[0] == LIBRARY[0]["text"]  # hints = checklist texts


def test_configured_key_produces_a_real_llm_explanation(real, http):
    r = P.assess_listing(L(**RISKY))
    assert len(http.calls) == 1 and http.calls[0].endswith("/chat/completions")
    assert r.explanation.source.value == "llm" and r.explanation.summary == GOOD["summary"]
    assert (r.llm_meta.provider, r.llm_meta.success, r.llm_meta.error_code) == ("groq", True, None)
    assert {c for k in r.explanation.key_concerns for c in k.evidence_ids} <= {e.id for e in r.evidence}


def test_score_level_evidence_checklist_entities_are_identical_whatever_the_llm_does(real, http):
    baseline = essentials(P.assess_listing(L(**RISKY), with_llm=False))
    outcomes = []
    for script in ([("ok", GOOD)], [("timeout",)], [("status", 503)], [("ok", {"summary": "This is a scam.", "key_concerns": [], "what_to_verify": []})],
                   [("ok", dict(GOOD, key_concerns=[{"text": "x", "evidence_ids": ["E99"]}]))]):
        P._RESULT_CACHE.clear()
        LC.reset_state()
        http.script[:] = script
        r = P.assess_listing(L(**RISKY), with_llm=True)
        outcomes.append(r.explanation.source.value)
        assert essentials(r) == baseline
    assert outcomes == ["llm", "template", "template", "template", "template"]
    LC.reset_state()
    assert essentials(P.assess_listing(L(**RISKY), with_llm=False)) == baseline
    clean_base = essentials(P.assess_listing(L(**CLEAN), with_llm=False))
    P._RESULT_CACHE.clear()
    assert essentials(P.assess_listing(L(**CLEAN), with_llm=True)) == clean_base


def test_llm_failure_never_breaks_the_assessment_and_is_reported_in_llm_meta(real, http):
    http.script[:] = [("timeout",)]
    r = P.assess_listing(L(**RISKY))
    assert r.explanation.source.value == "template" and r.risk_score > 0
    assert (r.llm_meta.provider, r.llm_meta.success, r.llm_meta.error_code) == ("template", False, "timeout")


def test_with_llm_false_never_touches_the_llm(real, http):
    r = P.assess_listing(L(**RISKY), with_llm=False)
    assert http.calls == [] and r.explanation.source.value == "template" and r.llm_meta.success is True


def test_a_failed_llm_attempt_is_not_cached_so_the_next_request_retries(real, http):
    http.script[:] = [("status", 500)]
    assert P.assess_listing(L(**RISKY)).explanation.source.value == "template"
    assert len(P._RESULT_CACHE) == 0
    assert P.assess_listing(L(**RISKY)).explanation.source.value == "llm" and len(http.calls) == 2


def test_successful_llm_result_is_served_from_the_result_cache(real, http):
    a = P.assess_listing(L(**RISKY))
    b = P.assess_listing(L(**RISKY))
    assert len(http.calls) == 1 and a.explanation.model_dump() == b.explanation.model_dump()
    assert b.llm_meta.provider == "groq" and b.llm_meta.latency_ms == 0  # no call was made for this response


def test_reload_clears_the_llm_cache_and_the_result_cache(real, http):
    P.assess_listing(L(**RISKY))
    assert len(http.calls) == 1
    P.reload_model()
    P.assess_listing(L(**RISKY))
    assert len(http.calls) == 2


def test_circuit_breaker_state_is_visible_through_the_pipeline(real, http):
    assert P.llm_circuit_open() is False
    http.script[:] = [("timeout",)] * 3
    for i in range(3):
        P.assess_listing(L(**dict(RISKY, title=f"Data Entry Intern {i}")))
    assert P.llm_circuit_open() is True and P.model_status()["llm_enabled"] is True
    n = len(http.calls)
    r = P.assess_listing(L(**dict(RISKY, title="Data Entry Intern 9")))
    assert len(http.calls) == n and r.llm_meta.error_code == "circuit_open" and r.explanation.source.value == "template"


def test_llm_enabled_without_a_key_uses_the_template(real, monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "true")
    r = P.assess_listing(L(**RISKY))
    assert r.explanation.source.value == "template" and r.llm_meta.error_code == "no_api_key" and P.model_status()["llm_enabled"] is True


def test_predict_never_calls_the_llm(real, http):
    P.predict_listing(L(**RISKY))
    assert http.calls == []
