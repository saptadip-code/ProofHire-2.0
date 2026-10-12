"""Evidence engine tests (Member 1, A-G4). Guidebook A7 / A15 test_evidence.py.

Observed rules need only pydantic. Model-derived evidence tests need the committed artifact to load in this
environment (scikit-learn 1.7.2) and skip, with the loader's reason, when it cannot.
Run: PYTHONPATH=backend pytest ml/tests -q
"""
import math
import re

import pytest

pytest.importorskip("pydantic")

from app.ml import evidence as E  # noqa: E402
from app.ml import features as F  # noqa: E402
from app.ml import model_store as S  # noqa: E402
from app.schemas.ml_schemas import EvidenceItem, ListingInput  # noqa: E402

TITLE = "Software Developer Intern"
MEDIAN = F.benchmark(F.detect_role(TITLE), "internship")
DESC = ("Join Nexora Labs and work with a mentor on our product. We run a structured interview and give weekly "
        "feedback to every intern. You will write and review code, fix bugs, document features and present your "
        "work to the team every two weeks during the programme. Apply through the careers page on our website.")
REQ = ("Comfortable with Python and version control, interest in testing, clear written communication and a "
       "willingness to learn from code review every week of the programme.")

BASE = dict(title=TITLE, company_name="Nexora Labs", description=DESC, requirements=REQ,
            contact_email="careers@nexora.com", company_website="https://www.nexora.com",
            application_channel="email", interview_mode="video_call")


def make(**kw) -> ListingInput:
    return ListingInput(**{**BASE, **kw})


def evid(listing=None, model=None, **kw):
    listing = listing or make(**kw)
    return E.build_evidence(listing, F.build_row(listing), model)


def codes(items):
    return [e.code for e in items]


# ------------------------------------------------------------------ catalogue
def test_catalogue_matches_guidebook_a7_table():
    assert E.OBSERVED_CODES == (
        "UPFRONT_FEE", "PERSONAL_DATA_REQUEST", "GUARANTEED_OFFER_CLAIM", "UNREALISTIC_PAY", "FREE_EMAIL_CONTACT",
        "EMAIL_DOMAIN_MISMATCH", "NO_COMPANY_WEBSITE", "MESSAGING_APP_ONLY", "URGENCY_PRESSURE", "NO_INTERVIEW",
        "VAGUE_DESCRIPTION", "VAGUE_REQUIREMENTS", "EXCESSIVE_HYPE", "CORP_EMAIL_MATCHES_WEBSITE",
        "DETAILED_REQUIREMENTS", "STRUCTURED_INTERVIEW", "PAY_IN_EXPECTED_RANGE")
    assert E.MODEL_CODES == ("MODEL_TERM", "MODEL_FEATURE")
    sev = {c: (s, d) for c, (s, d, _) in E.EVIDENCE_CATALOG.items()}
    assert sev == {
        "UPFRONT_FEE": (3, "increases_risk"), "PERSONAL_DATA_REQUEST": (3, "increases_risk"),
        "GUARANTEED_OFFER_CLAIM": (2, "increases_risk"), "UNREALISTIC_PAY": (3, "increases_risk"),
        "FREE_EMAIL_CONTACT": (2, "increases_risk"), "EMAIL_DOMAIN_MISMATCH": (2, "increases_risk"),
        "NO_COMPANY_WEBSITE": (1, "increases_risk"), "MESSAGING_APP_ONLY": (2, "increases_risk"),
        "URGENCY_PRESSURE": (1, "increases_risk"), "NO_INTERVIEW": (2, "increases_risk"),
        "VAGUE_DESCRIPTION": (1, "increases_risk"), "VAGUE_REQUIREMENTS": (1, "increases_risk"),
        "EXCESSIVE_HYPE": (1, "increases_risk"), "CORP_EMAIL_MATCHES_WEBSITE": (1, "decreases_risk"),
        "DETAILED_REQUIREMENTS": (1, "decreases_risk"), "STRUCTURED_INTERVIEW": (1, "decreases_risk"),
        "PAY_IN_EXPECTED_RANGE": (1, "decreases_risk")}


# ------------------------------------------------------------------ every observed code: fires / does not fire
# code -> (kwargs that make it fire, kwargs that make sure it does not). The BASE listing is a clean one.
CASES = {
    "UPFRONT_FEE": (dict(description=DESC + " Pay a registration fee of Rs 1,499 to confirm your seat."), {}),
    "PERSONAL_DATA_REQUEST": (dict(description=DESC + " Please send your Aadhaar and bank account number."), {}),
    "GUARANTEED_OFFER_CLAIM": (dict(description=DESC + " We offer 100% placement after the programme."), {}),
    "UNREALISTIC_PAY": (dict(salary_max=int(MEDIAN * 4)), dict(salary_max=int(MEDIAN * 2))),
    "FREE_EMAIL_CONTACT": (dict(contact_email="Nexora.Careers@Gmail.com"), {}),
    "EMAIL_DOMAIN_MISMATCH": (dict(contact_email="careers@nexora-jobs.in"), {}),
    "NO_COMPANY_WEBSITE": (dict(company_website=None), {}),
    "MESSAGING_APP_ONLY": (dict(application_channel="whatsapp"), dict(application_channel="phone")),
    "URGENCY_PRESSURE": (dict(description=DESC + " Apply now, only limited seats left!"), {}),
    "NO_INTERVIEW": (dict(interview_mode="chat_only"), {}),
    "VAGUE_DESCRIPTION": (dict(description="Easy data entry work from home, join today."), {}),
    "VAGUE_REQUIREMENTS": (dict(requirements="Good communication."), {}),
    "EXCESSIVE_HYPE": (dict(description=DESC + " Amazing!!! Great pay!!! Join now!!!"), {}),
    "CORP_EMAIL_MATCHES_WEBSITE": ({}, dict(contact_email="careers@gmail.com")),
    "DETAILED_REQUIREMENTS": ({}, dict(requirements="Python basics.")),
    "STRUCTURED_INTERVIEW": ({}, dict(interview_mode="none")),
    "PAY_IN_EXPECTED_RANGE": (dict(salary_max=int(MEDIAN)), dict(salary_max=int(MEDIAN * 2))),
}


def test_every_observed_code_has_a_case():
    assert set(CASES) == set(E.OBSERVED_CODES)


@pytest.mark.parametrize("code", E.OBSERVED_CODES)
def test_observed_code_fires_with_guidebook_attributes(code):
    fire, _ = CASES[code]
    items = evid(**fire)
    hit = [e for e in items if e.code == code]
    assert len(hit) == 1, f"{code} should appear exactly once, got {codes(items)}"
    e = hit[0]
    severity, direction, label = E.EVIDENCE_CATALOG[code]
    assert (e.type.value, e.direction.value, e.severity, e.label) == ("observed", direction, severity, label)
    assert e.weight is None  # observed weights are always null
    assert e.snippet is None or (isinstance(e.snippet, str) and 0 < len(e.snippet) <= 120)


@pytest.mark.parametrize("code", E.OBSERVED_CODES)
def test_observed_code_does_not_fire_when_condition_absent(code):
    _, quiet = CASES[code]
    assert code not in codes(evid(**quiet))


def test_clean_base_listing_only_has_protective_evidence():
    assert codes(evid()) == ["CORP_EMAIL_MATCHES_WEBSITE", "DETAILED_REQUIREMENTS", "STRUCTURED_INTERVIEW"]


def test_known_good_listing_yields_corp_email_matches_website():  # guidebook A15
    assert "CORP_EMAIL_MATCHES_WEBSITE" in codes(evid())


def test_known_risky_listing_yields_upfront_fee_with_snippet():  # guidebook A15
    items = evid(**CASES["UPFRONT_FEE"][0])
    fee = next(e for e in items if e.code == "UPFRONT_FEE")
    assert fee.snippet == "registration fee of Rs 1,499"


# ------------------------------------------------------------------ rule boundaries (A7 thresholds)
def _codes_for_features(**overrides):
    listing = make()
    f = dict(F.build_row(listing))
    f.update(overrides)
    return codes(E.build_evidence(listing, f))


@pytest.mark.parametrize("ratio,unrealistic,in_range", [
    (0.49, False, False), (0.5, False, True), (1.8, False, True), (1.81, False, False),
    (2.99, False, False), (3.0, True, False), (20.0, True, False), (0.0, False, False)])
def test_pay_rules_boundaries(ratio, unrealistic, in_range):
    got = _codes_for_features(salary_ratio_vs_role=ratio)
    assert ("UNREALISTIC_PAY" in got) is unrealistic
    assert ("PAY_IN_EXPECTED_RANGE" in got) is in_range


@pytest.mark.parametrize("hits,fires", [(0, False), (1, False), (2, True), (5, True)])
def test_urgency_needs_two_hits(hits, fires):
    assert ("URGENCY_PRESSURE" in _codes_for_features(urgency_hits=float(hits))) is fires


@pytest.mark.parametrize("exclaim,caps,fires", [(3, 0.25, False), (4, 0.0, True), (0, 0.2501, True), (0, 0.25, False)])
def test_hype_boundaries(exclaim, caps, fires):
    assert ("EXCESSIVE_HYPE" in _codes_for_features(exclaim_count=float(exclaim), caps_ratio=caps)) is fires


@pytest.mark.parametrize("words,vague", [(39, True), (40, False)])
def test_description_boundary(words, vague):
    assert ("VAGUE_DESCRIPTION" in _codes_for_features(desc_words=float(words))) is vague


@pytest.mark.parametrize("words,vague,detailed", [(7, True, False), (8, False, False), (24, False, False), (25, False, True)])
def test_requirements_boundaries(words, vague, detailed):
    got = _codes_for_features(req_words=float(words))
    assert ("VAGUE_REQUIREMENTS" in got) is vague and ("DETAILED_REQUIREMENTS" in got) is detailed


def test_protective_email_rule_is_exclusive_with_risky_email_rules():
    assert "CORP_EMAIL_MATCHES_WEBSITE" not in codes(evid(contact_email="careers@gmail.com"))
    assert "CORP_EMAIL_MATCHES_WEBSITE" not in codes(evid(contact_email="careers@nexora-jobs.in"))
    assert "CORP_EMAIL_MATCHES_WEBSITE" not in codes(evid(company_website=None))
    assert "FREE_EMAIL_CONTACT" not in codes(evid(contact_email="careers@nexora.com"))


def test_negated_fee_is_not_flagged():
    assert "UPFRONT_FEE" not in codes(evid(description=DESC + " There is no registration fee for applicants."))


def test_fee_field_alone_fires_upfront_fee_without_inventing_a_snippet():
    fee = next(e for e in evid(upfront_fee_amount=999) if e.code == "UPFRONT_FEE")
    assert fee.snippet is None


# ------------------------------------------------------------------ snippets: exact, <= 120, never invented
def _source_texts(listing):
    return [listing.title, listing.description, listing.requirements or "", listing.contact_email or ""]


RICH = dict(
    title="Data Entry Executive", company_name="Brightpath Careers", contact_email="Careers.HR@GMail.com",
    description=("URGENT HIRING!!! Earn big money from home. Pay a registration\nfee of Rs 1,499 to confirm your seat. "
                 "Send your Aadhaar and PAN card today. We offer Guaranteed Placement. Limited seats, Apply Now! "
                 "Wow!!! Great!!! Amazing opportunity for freshers with no interview required at all."),
    requirements="Typing.", upfront_fee_amount=1499, application_channel="telegram", interview_mode="chat_only",
    company_website=None, salary_max=int(F.benchmark("default", "internship") * 6))


def test_every_snippet_is_an_exact_span_of_the_submitted_text():
    listing = make(**RICH)
    items = evid(listing)
    texts = _source_texts(listing)
    with_snippet = [e for e in items if e.snippet is not None]
    assert with_snippet, "the rich listing should produce text snippets"
    for e in with_snippet:
        assert len(e.snippet) <= 120
        assert any(e.snippet in t for t in texts), (e.code, e.snippet)
        assert e.type.value == "observed"


def test_snippet_text_values_preserve_original_case_and_whitespace():
    by_code = {e.code: e for e in evid(make(**RICH))}
    assert by_code["UPFRONT_FEE"].snippet == "registration\nfee of Rs 1,499"  # exact, newline kept
    assert by_code["PERSONAL_DATA_REQUEST"].snippet == "Aadhaar"
    assert by_code["GUARANTEED_OFFER_CLAIM"].snippet == "Guaranteed Placement"
    assert by_code["FREE_EMAIL_CONTACT"].snippet == "Careers.HR@GMail.com"  # as submitted, not lower-cased
    assert by_code["URGENCY_PRESSURE"].snippet in {"URGENT HIRING", "Limited seats", "Apply Now"}


def test_hype_snippet_is_the_exclamation_clause():
    items = evid(description=DESC + " Amazing opportunity!!! Great pay!!! Join now!!!")
    hype = next(e for e in items if e.code == "EXCESSIVE_HYPE")
    assert hype.snippet.endswith("!!!") and "!" in hype.snippet and hype.snippet in make(
        description=DESC + " Amazing opportunity!!! Great pay!!! Join now!!!").description


def test_caps_only_hype_quotes_a_real_capitals_run():
    shout = "WORK FROM HOME AND EARN BIG MONEY EVERY SINGLE DAY WITHOUT ANY EFFORT AT ALL " * 3
    listing = make(description=shout + DESC)
    hype = next(e for e in evid(listing) if e.code == "EXCESSIVE_HYPE")
    assert hype.snippet and hype.snippet in listing.description


def test_rules_without_quotable_text_have_null_snippets():
    items = evid(make(**RICH))
    for code in ("UNREALISTIC_PAY", "NO_COMPANY_WEBSITE", "MESSAGING_APP_ONLY", "NO_INTERVIEW",
                 "VAGUE_REQUIREMENTS"):
        assert next(e for e in items if e.code == code).snippet is None


def test_clip_limits_snippets_to_120_characters():
    assert len(E._clip("x" * 500)) == 120 and E._clip("short") == "short"


# ------------------------------------------------------------------ ordering, ids, limits (observed only)
def test_observed_ordered_by_severity_then_table_order_and_ids_sequential():
    items = evid(make(**RICH))
    sev = [e.severity for e in items]
    assert sev == sorted(sev, reverse=True)
    assert [e.id for e in items] == [f"E{i}" for i in range(1, len(items) + 1)]
    table = {c: i for i, c in enumerate(E.OBSERVED_CODES)}
    for a, b in zip(items, items[1:]):
        if a.severity == b.severity:
            assert table[a.code] < table[b.code]


def test_ids_are_assigned_per_assessment_not_per_code():
    a = evid(make(**RICH))
    b = evid()
    assert a[0].id == b[0].id == "E1" and a[0].code != b[0].code


def test_all_items_are_valid_evidence_items():
    for e in evid(make(**RICH)):
        EvidenceItem.model_validate(e.model_dump())


def test_model_none_returns_observed_only():
    assert all(e.type.value == "observed" for e in evid(make(**RICH), model=None))


# ------------------------------------------------------------------ model-derived evidence (real artifact)
@pytest.fixture(scope="module")
def artifacts():
    pytest.importorskip("numpy")
    pytest.importorskip("sklearn")
    try:
        return S.load_artifacts()
    except S.ArtifactError as exc:
        pytest.skip(f"committed artifact cannot load here: {exc}")


@pytest.fixture(scope="module")
def model(artifacts):
    return artifacts.pipeline


RISKY_WORDING = make(description=DESC + " Pay a registration fee of Rs 1,499. Guaranteed placement. Send Aadhaar.",
                     application_channel="whatsapp")
MIXED = make(description=DESC + " Pay a security deposit of Rs 500 before joining.", salary_max=int(MEDIAN * 1.2))


def _model_items(items):
    return [e for e in items if e.type.value == "model"]


def test_model_items_follow_the_guidebook_format(model):
    items = evid(make(), model=model)
    m = _model_items(items)
    assert m, "a clean listing has non-zero model contributions"
    for e in m:
        assert e.code in E.MODEL_CODES and e.severity == 2 and e.snippet is None
        assert e.weight is not None and e.weight == round(e.weight, 4) and e.weight != 0
        assert e.direction.value == ("increases_risk" if e.weight > 0 else "decreases_risk")
        assert re.search(r"^(Wording often seen in (risky|legitimate) listings: '.+'|Model signal: .+)$", e.label)
        assert not re.search(r"\b(fraud|scam|fake)\b", e.label, re.I)  # a pattern, never a verdict on the employer


def test_top_five_positive_and_top_two_negative_contributions(model):
    listing = make()
    f = F.build_row(listing)
    contribs = E.model_contributions(listing, f, model)
    pos = sorted((round(c.value, 4) for c in contribs if round(c.value, 4) > 0), reverse=True)[:5]
    neg = sorted(round(c.value, 4) for c in contribs if round(c.value, 4) < 0)[:2]
    got = _model_items(E.build_evidence(listing, f, model))  # clean listing: 3 observed + 7 model <= 12, no cut
    assert sorted((e.weight for e in got if e.weight > 0), reverse=True) == pos
    assert sorted(e.weight for e in got if e.weight < 0) == neg
    assert len(pos) == 5 and len(neg) == 2  # both signs are available for this listing


def test_model_items_are_ordered_by_weight_descending_after_observed(model):
    items = evid(make(), model=model)
    kinds = [e.type.value for e in items]
    assert kinds == sorted(kinds, key=lambda k: k != "observed")  # all observed first
    weights = [e.weight for e in _model_items(items)]
    assert weights == sorted(weights, reverse=True)
    assert weights[0] > 0 > weights[-1]  # positive contributions precede negative ones
    assert [e.id for e in items] == [f"E{i}" for i in range(1, len(items) + 1)]


def test_representative_positive_and_negative_contributions(model):
    risky = _model_items(evid(RISKY_WORDING, model=model))
    legit = _model_items(evid(make(), model=model))
    assert any(e.weight > 0 for e in risky) and any(e.weight < 0 for e in legit)
    # the same structured feature can flip sign: description length is protective for a long, detailed text
    long_desc = [e for e in legit if e.label == "Model signal: length of the description"]
    assert long_desc and long_desc[0].weight < 0 and long_desc[0].direction.value == "decreases_risk"


def test_tfidf_terms_are_wording_patterns_present_in_the_text(model):
    listing = make()  # few structured features fire here, so TF-IDF terms reach the top five (see module note)
    words = set(re.findall(r"\b\w\w+\b", F.text_of(listing)))
    terms = [e for e in evid(listing, model=model) if e.code == "MODEL_TERM"]
    assert terms
    for e in terms:
        term = re.search(r"'(.+)'$", e.label).group(1)
        assert e.label.startswith("Wording often seen in ") and e.label.endswith(f"listings: '{term}'")
        assert all(w in words for w in term.split()), term  # wording from this listing, not a fact about the employer


def test_structured_feature_labels_are_human_readable(model):
    labels = [e.label for e in _model_items(evid(RISKY_WORDING, model=model)) if e.code == "MODEL_FEATURE"]
    for label in labels:
        assert label.startswith("Model signal: ") and "_" not in label  # no raw column names like salary_ratio_vs_role


def test_contributions_reproduce_the_model_score(model, artifacts):
    for listing in (make(), make(**RICH), MIXED):
        f = F.build_row(listing)
        logit = sum(c.value for c in E.model_contributions(listing, f, model)) + float(model.steps[-1][1].intercept_[0])
        assert math.isclose(1 / (1 + math.exp(-logit)), S.predict_score(artifacts, listing), abs_tol=1e-4)


def test_max_twelve_items_and_observed_never_displaced(model):
    items = evid(make(**RICH), model=model)
    assert len(items) == 12  # observed alone already reach the cap for this listing
    obs = [e for e in items if e.type.value == "observed"]
    assert len(obs) == len(evid(make(**RICH), model=None))  # every observed item survived the cap
    assert [e.id for e in items] == [f"E{i}" for i in range(1, len(items) + 1)]


def test_model_part_is_skipped_loudly_when_the_pipeline_cannot_be_explained(caplog):
    class NotAPipeline:
        steps = []

    with caplog.at_level("ERROR", logger="proofhire.ml"):
        items = evid(make(), model=NotAPipeline())
    assert codes(items) == ["CORP_EMAIL_MATCHES_WEBSITE", "DETAILED_REQUIREMENTS", "STRUCTURED_INTERVIEW"]
    assert any("model-derived evidence skipped" in r.message for r in caplog.records)


def test_column_map_matches_the_fitted_transformer(model):
    entries = E._column_entries(model)
    names = model.steps[0][1].get_feature_names_out()
    assert len(entries) == len(names) == model.steps[-1][1].coef_.shape[1]
    for (kind, name, _), full in zip(entries, names):
        assert full.startswith("tfidf__") == (kind == "term")
        if kind == "term":
            assert full == f"tfidf__{name}"
    assert E._column_entries(model) is entries  # cached for the same model object
