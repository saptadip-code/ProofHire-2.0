"""Explainable pipeline integration (Member 1, A-G4): real score + evidence + checklist + entities + template
explanation, the result cache, and the invariants that tie them together. Guidebook A2 / A7-A9 / A12 / A15.
Needs pydantic, numpy and scikit-learn 1.7.2 (the committed artifact must load). Run: PYTHONPATH=backend pytest ml/tests -q
"""
import inspect
import json

import pytest

pytest.importorskip("pydantic")
pytest.importorskip("sklearn")

from app.ml import checklist as C  # noqa: E402
from app.ml import evidence as E  # noqa: E402
from app.ml import pipeline as P  # noqa: E402
from app.ml import template_explainer as T  # noqa: E402
from app.schemas.ml_schemas import ListingInput, MlResult  # noqa: E402

CLEAN = dict(
    title="Software Developer Intern", company_name="Nexora Technologies Pvt. Ltd.",
    description=("Join Nexora and work with a mentor on our product. We run a structured interview and give weekly "
                 "feedback to every intern. You will write and review code, fix bugs, document features and present "
                 "your work to the team every two weeks during the programme. Apply through our careers page."),
    requirements=("Comfortable with Python and version control, interest in testing, clear written communication and a "
                  "willingness to learn from code review every week of the programme."),
    contact_email="careers@nexora.com", contact_phone="+91 98765 43210", company_website="https://www.nexora.com",
    application_channel="email", interview_mode="video_call", salary_min=15000, salary_max=25000)
RISKY = dict(
    title="Data Entry Intern", company_name="Brightpath Careers",
    description="Work from home. Pay registration fee of Rs 1,499 to confirm your seat. Send Aadhaar today. Apply now, limited seats!",
    contact_email="Brightpath.HR@Gmail.com", upfront_fee_amount=1499, application_channel="whatsapp",
    interview_mode="chat_only", salary_max=90000)

LIBRARY = [
    {"code": "CHK_NO_FEE", "text": "Never pay any fee before a signed offer.", "priority": 1, "triggers": ["UPFRONT_FEE"]},
    {"code": "CHK_DATA", "text": "Never share ID or OTP details.", "priority": 1, "triggers": ["PERSONAL_DATA_REQUEST"]},
    {"code": "CHK_LEGAL_NAME", "text": "Look up the legal name in MCA search.", "priority": 2,
     "triggers": ["NO_COMPANY_WEBSITE", "EMAIL_DOMAIN_MISMATCH", "FREE_EMAIL_CONTACT"]},
    {"code": "CHK_GENERAL_RECRUITER", "text": "Find the recruiter on the official page.", "priority": 3, "triggers": ["*"]},
]


def L(**kw):
    return ListingInput(**kw)


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


# ------------------------------------------------------------------ the assembled result
def test_result_is_schema_valid_with_real_score(real):
    r = P.assess_listing(L(**RISKY), with_llm=False)
    MlResult.model_validate(r.model_dump())
    assert 0.0 <= r.risk_score <= 1.0 and r.risk_score == round(r.risk_score, 4)
    assert r.model_version == P.get_model_info()["model_version"]
    assert r.thresholds.model_dump() == P.get_model_info()["thresholds"]


def test_score_equals_the_prediction_only_path(real):
    for kw in (CLEAN, RISKY):
        assert P.assess_listing(L(**kw)).risk_score == P.predict_listing(L(**kw))["risk_score"]


def test_risk_level_comes_from_metadata_thresholds(real):
    th = P.get_model_info()["thresholds"]
    for kw in (CLEAN, RISKY):
        r = P.assess_listing(L(**kw))
        expected = "high" if r.risk_score >= th["high"] else "low" if r.risk_score < th["low"] else "medium"
        assert r.risk_level.value == expected


def test_risky_listing_is_high_and_clean_listing_is_low_with_matching_evidence(real):
    risky, clean = P.assess_listing(L(**RISKY)), P.assess_listing(L(**CLEAN))
    assert risky.risk_level.value == "high" and clean.risk_level.value == "low"
    rc = [e.code for e in risky.evidence]
    assert rc[:3] == ["UPFRONT_FEE", "PERSONAL_DATA_REQUEST", "UNREALISTIC_PAY"]
    assert "CORP_EMAIL_MATCHES_WEBSITE" in [e.code for e in clean.evidence]
    assert clean.explanation.key_concerns == []  # nothing risk-increasing was observed


def test_evidence_ids_are_sequential_and_observed_precede_model(real):
    r = P.assess_listing(L(**CLEAN))
    assert [e.id for e in r.evidence] == [f"E{i}" for i in range(1, len(r.evidence) + 1)] and len(r.evidence) <= 12
    types = [e.type.value for e in r.evidence]
    assert "observed" in types and "model" in types and types == sorted(types, key=lambda t: t != "observed")
    assert all(e.weight is None for e in r.evidence if e.type.value == "observed")
    assert all(e.weight is not None for e in r.evidence if e.type.value == "model")


def test_pipeline_evidence_equals_the_evidence_module_output(real):
    from app.ml import features as F

    r = P.assess_listing(L(**CLEAN))
    state = P._require_state()
    assert [e.model_dump() for e in r.evidence] == [e.model_dump() for e in
                                                    E.build_evidence(L(**CLEAN), F.build_row(L(**CLEAN)), state.pipeline)]


def test_every_explanation_reference_is_a_valid_evidence_id(real):
    for kw in (CLEAN, RISKY, dict(RISKY, application_channel="email", interview_mode="video_call", salary_max=None)):
        r = P.assess_listing(L(**kw))
        ids = {e.id for e in r.evidence}
        for concern in r.explanation.key_concerns:
            assert concern.evidence_ids and set(concern.evidence_ids) <= ids
        assert r.explanation.source.value == "template" and r.llm_meta.provider == "template"


def test_template_concerns_cite_the_evidence_they_describe(real):
    r = P.assess_listing(L(**RISKY))
    by_id = {e.id: e for e in r.evidence}
    first = r.explanation.key_concerns[0]
    assert first.evidence_ids == ["E1"] and by_id["E1"].code == "UPFRONT_FEE"
    for c in r.explanation.key_concerns:
        refs = [by_id[i] for i in c.evidence_ids]
        assert all(e.direction.value == "increases_risk" for e in refs)
        if not c.text.startswith(T.MODEL_CONCERN_PREFIX):
            assert [e.type.value for e in refs] == ["observed"]
        else:
            assert all(e.type.value == "model" for e in refs)


def test_checklist_is_built_from_this_assessments_evidence(real):
    r = P.assess_listing(L(**RISKY))
    codes = [c.code for c in r.checklist]
    assert codes == ["CHK_NO_FEE", "CHK_DATA", "CHK_LEGAL_NAME", "CHK_GENERAL_RECRUITER"]
    clean = [c.code for c in P.assess_listing(L(**CLEAN)).checklist]
    assert clean == ["CHK_GENERAL_RECRUITER"]  # no trigger fired: only the always-on item
    assert all("id" not in c.model_dump() and c.done is False for c in r.checklist)


def test_entities_follow_a9(real):
    r = P.assess_listing(L(**CLEAN))
    assert [(e.type.value, e.value) for e in r.entities] == [
        ("email", "careers@nexora.com"), ("email_domain", "nexora.com"), ("phone", "9876543210"),
        ("website_domain", "nexora.com"), ("company_name", "nexora")]
    risky = P.assess_listing(L(**RISKY))
    assert [(e.type.value, e.value) for e in risky.entities] == [
        ("email", "brightpath.hr@gmail.com"), ("company_name", "brightpath careers")]  # no free-mail email_domain


def test_missing_checklist_library_does_not_break_assessments(real, tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(C, "LIBRARY_PATH", tmp_path / "does_not_exist.json")
    C.clear_cache()
    with caplog.at_level("ERROR", logger="proofhire.ml"):
        r = P.assess_listing(L(**RISKY))
    assert r.checklist == [] and r.evidence and r.risk_score > 0
    assert C.library_status()["status"] == "missing" and any("MISSING" in m.message for m in caplog.records)


# ------------------------------------------------------------------ explanation can never touch score / level
def test_explanation_builder_receives_only_level_evidence_and_hints():
    assert list(inspect.signature(T.build_template_explanation).parameters) == ["risk_level", "evidence", "checklist_hints"]


def test_a_misbehaving_explainer_cannot_change_score_or_level(real, monkeypatch):
    expected = P.predict_listing(L(**RISKY))

    def evil(risk_level, evidence, checklist_hints=None):
        evidence[:] = []  # tries to tamper with its inputs; the score/level were fixed before this call
        return T.Explanation(source="template", summary="x", key_concerns=[], what_to_verify=[])

    monkeypatch.setattr(P.template_explainer, "build_template_explanation", evil)
    r = P.assess_listing(L(**RISKY))
    assert (r.risk_score, r.risk_level.value) == (expected["risk_score"], expected["risk_level"])
    assert r.evidence and r.evidence[0].code == "UPFRONT_FEE"  # the explainer only ever saw a copy of the evidence


def test_template_text_never_declares_fraud(real):
    for kw in (CLEAN, RISKY):
        r = P.assess_listing(L(**kw))
        text = " ".join([r.explanation.summary, *[c.text for c in r.explanation.key_concerns], *r.explanation.what_to_verify]).lower()
        assert not any(w in text for w in ("is a scam", "is fraudulent", "is fake", "definitely", "certainly"))


def test_template_unit_levels_and_model_concern_rules():
    from app.schemas.ml_schemas import EvidenceItem

    obs = EvidenceItem(id="E1", code="UPFRONT_FEE", label="l", type="observed", direction="increases_risk", severity=3)
    mod = EvidenceItem(id="E2", code="MODEL_TERM", label="m", type="model", direction="increases_risk", severity=2, weight=0.4)
    prot = EvidenceItem(id="E3", code="STRUCTURED_INTERVIEW", label="p", type="observed", direction="decreases_risk", severity=1)
    for level in ("high", "medium"):
        x = T.build_template_explanation(level, [obs, mod, prot])
        assert [c.evidence_ids for c in x.key_concerns] == [["E1"], ["E2"]]
    low = T.build_template_explanation("low", [obs, mod, prot])
    assert [c.evidence_ids for c in low.key_concerns] == [["E1"]]  # no model concern at low risk
    assert T.build_template_explanation("high", []).key_concerns == []
    assert T.build_template_explanation("low", []).what_to_verify == [T.GENERIC_VERIFY]  # no hint supplied -> one fixed sentence


# ------------------------------------------------------------------ result cache (A12)
def test_cache_constants_follow_the_guidebook():
    assert P.RESULT_CACHE_MAX_ENTRIES == 100 and P.RESULT_CACHE_TTL_SECONDS == 600


def test_identical_listing_is_served_from_cache(real, monkeypatch):
    calls = []
    orig = P.evidence_mod.build_evidence
    monkeypatch.setattr(P.evidence_mod, "build_evidence", lambda *a, **k: calls.append(1) or orig(*a, **k))
    a = P.assess_listing(L(**RISKY), with_llm=False)
    b = P.assess_listing(L(**RISKY), with_llm=False)
    assert len(calls) == 1 and a.model_dump() == b.model_dump() and a is not b  # deep copy: callers cannot corrupt the cache
    b.evidence.clear()
    assert P.assess_listing(L(**RISKY), with_llm=False).evidence  # unaffected by the mutation above


def test_any_listing_change_misses_the_cache(real, monkeypatch):
    calls = []
    orig = P.evidence_mod.build_evidence
    monkeypatch.setattr(P.evidence_mod, "build_evidence", lambda *a, **k: calls.append(1) or orig(*a, **k))
    P.assess_listing(L(**RISKY))
    P.assess_listing(L(**dict(RISKY, upfront_fee_amount=1500)))
    P.assess_listing(L(**dict(RISKY, contact_email="Brightpath.hr@gmail.com")))  # case differs -> different snippets
    assert len(calls) == 3


def test_default_values_normalise_to_the_same_key(real):
    state = P._require_state()
    a = L(title="Data Entry Intern", company_name="Brightpath", description="x" * 30)
    b = L(title="Data Entry Intern", company_name="Brightpath", description="x" * 30, work_mode="onsite",
          currency="INR", upfront_fee_amount=0, interview_mode="none")
    assert P._result_cache_key(a, state, False) == P._result_cache_key(b, state, False)


def test_key_depends_on_the_effective_llm_mode_and_model_identity(real):
    state = P._require_state()
    listing = L(**RISKY)
    assert P._result_cache_key(listing, state, False) != P._result_cache_key(listing, state, True)
    other = P.store.LoadedArtifacts(pipeline=state.pipeline, meta={**state.meta, "model_version": "proofhire-lr-9.9.9"},
                                    metrics=None, sha256=state.sha256)
    assert P._result_cache_key(listing, state, False) != P._result_cache_key(listing, other, False)
    other_th = P.store.LoadedArtifacts(pipeline=state.pipeline, meta={**state.meta, "thresholds": {"low": 0.1, "high": 0.2}},
                                       metrics=None, sha256=state.sha256)
    assert P._result_cache_key(listing, state, False) != P._result_cache_key(listing, other_th, False)


def _fake_llm_ok(monkeypatch, calls):
    """LLM switched on with a fake provider that answers with a valid explanation citing E1 (no network)."""
    from app.ml import llm_client as LC

    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_API_KEY", "test-key-not-real")
    LC.reset_state()

    def post(url, api_key, body, timeout):
        calls.append(url)
        content = json.dumps({"summary": "Several signals deserve a careful check.",
                              "key_concerns": [{"text": "A fee is requested.", "evidence_ids": ["E1"]}],
                              "what_to_verify": ["Ask the company for a written offer."]})
        return 200, json.dumps({"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr(LC, "_post_json", post)


def test_with_llm_false_never_reuses_an_llm_enabled_entry(real, monkeypatch):
    calls = []
    _fake_llm_ok(monkeypatch, calls)
    a = P.assess_listing(L(**RISKY), with_llm=True)  # LLM-enabled entry
    assert len(calls) == 1 and a.explanation.source.value == "llm"
    b = P.assess_listing(L(**RISKY), with_llm=False)  # evidence-only caller: must not be handed the entry above
    assert b.explanation.source.value == "template" and b.llm_meta.provider == "template" and len(calls) == 1
    assert P.assess_listing(L(**RISKY), with_llm=True).explanation.source.value == "llm"
    assert P.assess_listing(L(**RISKY), with_llm=False).explanation.source.value == "template"
    assert len(calls) == 1  # each mode is cached separately; the LLM was called exactly once
    monkeypatch.setenv("LLM_ENABLED", "false")
    c = P.assess_listing(L(**RISKY), with_llm=True)  # LLM switched off: effective mode is template-only
    assert c.explanation.source.value == "template" and len(calls) == 1


def test_cache_payload_holds_only_listing_fields_and_model_identity(real):
    state = P._require_state()
    seen = {}
    real_dumps = json.dumps

    def spy(obj, **kw):
        seen["payload"] = obj
        return real_dumps(obj, **kw)

    P.json.dumps = spy
    try:
        P._result_cache_key(L(**RISKY), state, False)
    finally:
        P.json.dumps = real_dumps
    payload = seen["payload"]
    assert set(payload) == {"listing", "model_version", "model_sha256", "thresholds", "llm"}
    assert set(payload["listing"]) == set(ListingInput.model_fields)  # nothing user-specific can be in a ListingInput
    assert not {"user", "user_id", "owner_token", "jwt", "token", "authorization"} & set(payload["listing"])


def test_failed_assessment_is_not_cached(tmp_path, monkeypatch):
    from app.ml import model_store as S

    monkeypatch.setattr(S, "ARTIFACT_DIR", tmp_path)  # nothing to load
    P._reset_for_tests()
    with pytest.raises(P.ModelNotLoadedError):
        P.assess_listing(L(**RISKY))
    assert len(P._RESULT_CACHE) == 0
    P._reset_for_tests()


def test_reload_clears_the_result_cache(real):
    P.assess_listing(L(**RISKY))
    assert len(P._RESULT_CACHE) == 1
    P.reload_model()
    assert len(P._RESULT_CACHE) == 0


# ------------------------------------------------------------------ the cache class itself
class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _result(real, n=0):
    return P.assess_listing(L(**dict(CLEAN, title=f"Software Developer Intern {n}")))


def test_ttl_expiry(real):
    clock = FakeClock()
    c = P._ResultCache(100, 600, clock)
    r = _result(real)
    c.put("k", r)
    clock.t += 599.9
    assert c.get("k") is not None
    clock.t += 0.2  # 600.1 s after the put: expired
    assert c.get("k") is None and len(c) == 0


def test_max_100_entries_evicts_least_recently_used(real):
    c = P._ResultCache(100, 600, FakeClock())
    r = _result(real)
    for i in range(100):
        c.put(f"k{i}", r)
    assert len(c) == 100
    assert c.get("k0") is not None  # touching k0 makes k1 the oldest
    c.put("k100", r)
    assert len(c) == 100 and c.get("k1") is None and c.get("k0") is not None and c.get("k100") is not None
    for i in range(101, 300):
        c.put(f"k{i}", r)
    assert len(c) == 100


def test_cache_returns_independent_copies(real):
    c = P._ResultCache(10, 600, FakeClock())
    c.put("k", _result(real))
    a = c.get("k")
    a.risk_score = 0.0
    a.evidence.clear()
    b = c.get("k")
    assert b.risk_score > 0 and b.evidence


def test_module_cache_uses_guidebook_limits(real):
    assert (P._RESULT_CACHE._max, P._RESULT_CACHE._ttl) == (100, 600)
