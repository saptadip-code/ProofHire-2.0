"""Template explainer unit tests (Member 1, A-G5): deterministic, network free, uses only supplied evidence / hints."""
import pytest

pytest.importorskip("pydantic")

from app.ml import template_explainer as T  # noqa: E402
from app.schemas.ml_schemas import EvidenceItem  # noqa: E402


def ev(i, code="UPFRONT_FEE", label="Asks the applicant to pay money", type_="observed", direction="increases_risk",
       snippet="registration fee of Rs 1,499", weight=None):
    return EvidenceItem(id=f"E{i}", code=code, label=label, type=type_, direction=direction, severity=2, snippet=snippet, weight=weight)


OBS = ev(1)
OBS2 = ev(2, "NO_COMPANY_WEBSITE", "No company website is given", snippet=None)
MOD = ev(3, "MODEL_TERM", "Wording often seen in risky listings: 'guaranteed placement'", "model", snippet=None, weight=1.8)
MOD2 = ev(4, "MODEL_FEATURE", "Model signal: a contact email is given", "model", snippet=None, weight=0.9)
PROT = ev(5, "STRUCTURED_INTERVIEW", "A video, in-person or phone interview is offered", direction="decreases_risk", snippet=None)
HINTS = ["Never pay any fee before a signed offer.", "Find the recruiter on the official page."]


def texts(x):
    return [x.summary, *[c.text for c in x.key_concerns], *x.what_to_verify]


def test_output_structure_and_source():
    x = T.build_template_explanation("high", [OBS, MOD], HINTS)
    assert x.source.value == "template" and x.summary
    assert all(c.text and c.evidence_ids for c in x.key_concerns) and all(isinstance(v, str) for v in x.what_to_verify)


def test_concern_uses_the_supplied_label_and_exact_snippet():
    x = T.build_template_explanation("high", [OBS, OBS2], HINTS)
    assert x.key_concerns[0].text == 'Asks the applicant to pay money. The listing says: "registration fee of Rs 1,499"'
    assert x.key_concerns[0].evidence_ids == ["E1"]
    assert x.key_concerns[1].text == "No company website is given." and x.key_concerns[1].evidence_ids == ["E2"]


def test_only_supplied_hints_become_what_to_verify():
    x = T.build_template_explanation("high", [OBS], HINTS + [HINTS[0], "", None, 5])
    assert x.what_to_verify == HINTS  # deduplicated, non-strings dropped, nothing invented
    assert T.build_template_explanation("high", [OBS], None).what_to_verify == [T.GENERIC_VERIFY]
    assert T.build_template_explanation("high", [OBS], []).what_to_verify == [T.GENERIC_VERIFY]
    many = T.build_template_explanation("high", [OBS], [f"hint {i}" for i in range(9)])
    assert many.what_to_verify == [f"hint {i}" for i in range(5)]


def test_model_concern_cites_model_evidence_only_at_medium_or_high():
    for level in ("high", "medium"):
        x = T.build_template_explanation(level, [OBS, MOD, MOD2, PROT], HINTS)
        assert [c.evidence_ids for c in x.key_concerns] == [["E1"], ["E3", "E4"]]
        assert x.key_concerns[1].text.startswith(T.MODEL_CONCERN_PREFIX) and "guaranteed placement" in x.key_concerns[1].text
    low = T.build_template_explanation("low", [OBS, MOD, PROT], HINTS)
    assert [c.evidence_ids for c in low.key_concerns] == [["E1"]]


def test_protective_evidence_never_becomes_a_concern():
    assert T.build_template_explanation("low", [PROT], HINTS).key_concerns == []


def test_limits():
    many = [ev(i, snippet=f"s{i}") for i in range(1, 10)]
    x = T.build_template_explanation("high", many + [MOD], HINTS)
    assert len(x.key_concerns) == 5
    long = ev(1, label="L" * 250, snippet="S" * 300)
    t = T.build_template_explanation("high", [long], HINTS).key_concerns[0].text
    assert len(t) <= 300 and t.endswith("...")


def test_control_characters_in_snippets_are_removed():
    t = T.build_template_explanation("high", [ev(1, snippet="line1\nline2\x00\x1b[0m   end")], HINTS).key_concerns[0].text
    assert "\n" not in t and "\x00" not in t and "\x1b" not in t


@pytest.mark.parametrize("level,fragment", [("high", "risk estimate"), ("medium", "risk estimate"), ("low", "risk estimate")])
def test_summary_is_cautious(level, fragment):
    x = T.build_template_explanation(level, [OBS, MOD], HINTS)
    assert fragment in x.summary and len(x.summary) <= 700
    low = " ".join(texts(x)).lower()
    assert not any(w in low for w in ("is a scam", "is fraudulent", "is fake", "definitely", "certainly", "guaranteed to be"))


def test_unknown_level_falls_back_to_the_medium_wording():
    assert T.build_template_explanation("weird", [OBS], HINTS).summary == T.SUMMARY["medium"]


def test_deterministic_and_pure():
    a = T.build_template_explanation("high", [OBS, MOD], HINTS)
    b = T.build_template_explanation("high", [OBS, MOD], HINTS)
    assert a.model_dump() == b.model_dump()
    items = [OBS, MOD]
    T.build_template_explanation("high", items, HINTS)
    assert items == [OBS, MOD]


def test_every_cited_id_exists_in_the_evidence():
    items = [OBS, OBS2, MOD, MOD2, PROT]
    ids = {e.id for e in items}
    for level in ("low", "medium", "high"):
        for c in T.build_template_explanation(level, items, HINTS).key_concerns:
            assert set(c.evidence_ids) <= ids
