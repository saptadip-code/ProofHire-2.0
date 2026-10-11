"""Schema validation tests (Member 1). Run: PYTHONPATH=backend pytest ml/tests -q"""
import pytest
from pydantic import ValidationError

from app.schemas.ml_schemas import ListingInput, MlResult
from app.ml.pipeline import assess_listing
from app.ml.entities import FREE_MAIL_DOMAINS

BASE = {"title": "Intern", "company_name": "Nexora Labs",
        "description": "A reasonably long description of the role."}


def make(**kw):
    return ListingInput(**{**BASE, **kw})


def test_defaults():
    l = make()
    assert (l.work_mode.value, l.employment_type.value, l.pay_period.value) == ("onsite", "internship", "month")
    assert (l.currency, l.application_channel.value, l.upfront_fee_amount, l.interview_mode.value) == \
        ("INR", "unknown", 0, "none")


@pytest.mark.parametrize("kw", [
    {"title": "ab"}, {"company_name": "a"}, {"description": "too short"},
    {"description": "x" * 8001}, {"requirements": "x" * 4001}, {"location": "x" * 201},
    {"salary_min": -1}, {"salary_min": 10, "salary_max": 5}, {"currency": "RS"},
    {"contact_email": "not-an-email"}, {"contact_phone": "abc"}, {"contact_phone": "1" * 33},
    {"company_website": "example.com"}, {"upfront_fee_amount": -1},
    {"work_mode": "office"}, {"interview_mode": "zoom"},
])
def test_invalid_inputs_rejected(kw):
    with pytest.raises(ValidationError):
        make(**kw)


def test_valid_edge_inputs():
    make(salary_min=5, salary_max=5, contact_phone="+91 (98765) 43210",
         company_website="https://nexora.com", contact_email="a@b.co", requirements=None)


def test_assess_listing_result_matches_schema():
    """A-G3: real score; evidence/checklist are interim (empty) until A-G4. Skips if the artifact cannot load here."""
    from app.ml import pipeline

    pipeline._reset_for_tests()
    try:
        r = assess_listing(make(upfront_fee_amount=999))
    except pipeline.ModelNotLoadedError as exc:
        pytest.skip(f"committed artifact cannot load in this environment: {exc}")
    MlResult.model_validate(r.model_dump())
    assert 0.0 <= r.risk_score <= 1.0
    assert r.risk_level.value in {"low", "medium", "high"}
    assert r.evidence == [] and r.checklist == []  # interim until A-G4 (never fabricated)


def test_free_mail_domains_contract():
    assert FREE_MAIL_DOMAINS == {"gmail.com", "outlook.com", "yahoo.com",
                                 "hotmail.com", "proton.me", "rediffmail.com"}
