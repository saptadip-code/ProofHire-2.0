"""A-G2 feature tests (Member 1). Run: pytest ml/tests -q

Covers: feature names/order, A15 cases (fee regex, free-mail, yearly->monthly), missing/empty inputs,
runtime constraints (no pandas), runtime JSON files in sync with ml/data/lexicons.py.
"""
import json
import math
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.ml import features as F
from app.ml.entities import FREE_MAIL_DOMAINS

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "backend" / "app" / "data"

EXPECTED_NUM = ["salary_max_month_log", "salary_ratio_vs_role", "salary_spread", "desc_words", "req_words",
                "exclaim_count", "caps_ratio", "urgency_hits", "fee_amount_log"]
EXPECTED_BIN = ["has_upfront_fee", "asks_personal_data", "guaranteed_claim", "no_experience_hype", "email_is_free",
                "email_present", "website_missing", "domain_mismatch", "messaging_only", "no_interview",
                "vague_desc", "vague_requirements", "phone_present"]
EXPECTED_CAT = ["work_mode", "employment_type", "application_channel", "interview_mode"]

BASE = {"title": "Data Analyst Intern", "company_name": "Nexora Labs",
        "description": "A reasonably long description of the role. " * 10}

RISKY = {
    "title": "Data Entry Intern - Earn 40000 per month!!", "company_name": "Brightpath Careers",
    "description": "Work from home. No experience needed. Pay registration fee of Rs 1,499 to confirm your seat. "
                   "Apply now, limited seats! Send Aadhaar and bank account on WhatsApp. 100% placement guaranteed.",
    "salary_min": 40000, "salary_max": 40000, "pay_period": "month", "contact_email": "brightpath.hr@gmail.com",
    "application_channel": "whatsapp", "upfront_fee_amount": 1499, "interview_mode": "chat_only",
}
GOOD = {
    "title": "Software Engineer", "company_name": "Veltrix Technologies",
    "description": ("Veltrix Technologies is hiring a software engineer to build backend services. You will work with "
                    "a mentor, review code weekly and ship small features. ") * 3,
    "requirements": "Working knowledge of Python and SQL. Good communication with teammates. Degree in a relevant "
                    "field or equivalent projects. Comfortable with Git and code review. Reliable follow-through.",
    "salary_min": 70000, "salary_max": 90000, "contact_email": "careers@veltrix.com", "company_website": "https://www.veltrix.com",
    "application_channel": "email", "interview_mode": "video_call", "employment_type": "full_time",
    "contact_phone": "9876543210",
}


def row(**kw):
    return F.build_row({**BASE, **kw})


# ---------------------------------------------------------------- names / order
def test_feature_names_and_order_match_guidebook():
    assert F.NUM_COLS == EXPECTED_NUM
    assert F.BIN_COLS == EXPECTED_BIN
    assert F.CAT_COLS == EXPECTED_CAT
    assert F.FEATURE_ORDER == EXPECTED_NUM + EXPECTED_BIN + EXPECTED_CAT
    assert len(F.FEATURE_ORDER) == 26 and len(set(F.FEATURE_ORDER)) == 26
    assert F.TEXT_COL == "text"


def test_build_row_keys_follow_feature_order_and_types():
    r = F.build_row(RISKY)
    assert list(r.keys()) == F.FEATURE_ORDER
    for c in F.NUM_COLS:
        assert isinstance(r[c], float) and math.isfinite(r[c])
    for c in F.BIN_COLS:
        assert r[c] in (0, 1) and isinstance(r[c], int)
    for c in F.CAT_COLS:
        assert r[c] in F.CAT_VALUES[c]
    assert list(F.build_model_row(RISKY).keys()) == F.FEATURE_ORDER + ["text"]


# ---------------------------------------------------------------- A15 cases
def test_fee_regex_finds_registration_fee_of_rs_1499():
    m = F.search_lexicon("fee", "Pay registration fee of Rs 1,499 to confirm.")
    assert m is not None and m.group(0).lower() == "registration fee"
    assert row(description="Please pay registration fee of Rs 1,499 to confirm your seat today.")["has_upfront_fee"] == 1


@pytest.mark.parametrize("text", [
    "There is no registration fee or deposit of any kind at any stage in hiring.",
    "We never charge any processing fee from applicants at all.",
    "Applicants are not asked to pay any security deposit during hiring.",
])
def test_negated_fee_mentions_are_ignored(text):
    assert F.search_lexicon("fee", text) is None
    assert row(description=text + " Padding words to be long enough here.")["has_upfront_fee"] == 0


def test_fee_field_alone_sets_has_upfront_fee():
    r = row(upfront_fee_amount=999)
    assert r["has_upfront_fee"] == 1 and r["fee_amount_log"] == pytest.approx(math.log1p(999))


@pytest.mark.parametrize("email,free", [
    ("hr@gmail.com", 1), ("x@Outlook.com", 1), ("a@yahoo.com", 1), ("a@hotmail.com", 1), ("a@proton.me", 1),
    ("a@rediffmail.com", 1), ("careers@nexora.com", 0), ("", 0), (None, 0),
])
def test_free_mail_detection(email, free):
    r = row(contact_email=email)
    assert r["email_is_free"] == free
    assert r["email_present"] == int(bool(email))


def test_yearly_salary_is_normalised_to_monthly():
    monthly = row(salary_min=40000, salary_max=50000, pay_period="month")
    yearly = row(salary_min=480000, salary_max=600000, pay_period="year")
    assert yearly["salary_max_month_log"] == pytest.approx(math.log1p(50000))
    assert yearly["salary_max_month_log"] == pytest.approx(monthly["salary_max_month_log"])
    assert yearly["salary_ratio_vs_role"] == pytest.approx(monthly["salary_ratio_vs_role"])
    assert F.to_monthly(120000, "year") == 10000 and F.to_monthly(5000, "month") == 5000


# ---------------------------------------------------------------- feature definitions
def test_salary_features_caps_and_absence():
    none = row()
    assert none["salary_max_month_log"] == 0 and none["salary_ratio_vs_role"] == 0 and none["salary_spread"] == 0
    r = row(salary_min=1, salary_max=10_000_000)
    assert r["salary_ratio_vs_role"] == 20.0 and r["salary_spread"] == 10.0
    assert row(salary_min=1000, salary_max=2000)["salary_spread"] == pytest.approx(2.0)


def test_role_benchmark_lookup():
    assert F.detect_role("Data Analyst Intern") == "data analysis"
    assert F.detect_role("Software Engineer") == "software engineering"
    assert F.detect_role("Quantum Gardener") == "default"
    assert F.benchmark("data analysis", "internship") == 20000
    assert F.benchmark("default", "full_time") == 35000
    # 40,000 for an internship data-entry role is 5x the synthetic median
    r = F.build_row({**RISKY, "employment_type": "internship"})
    assert r["salary_ratio_vs_role"] == pytest.approx(40000 / 8000)


def test_counts_caps_and_hype_features():
    r = F.build_row({**BASE, "title": "URGENT HIRING!!!", "description": "WORK FROM HOME!!! EARN MORE!!! " * 6})
    assert r["exclaim_count"] == 15.0  # capped
    assert r["caps_ratio"] > 0.9
    assert F.build_row(BASE)["exclaim_count"] == 0
    assert row(description="Apply now! Limited seats! Hurry up, last date today. " + "x " * 20)["urgency_hits"] == 4.0


def test_binary_features_on_risky_listing():
    r = F.build_row(RISKY)
    for c in ["has_upfront_fee", "asks_personal_data", "guaranteed_claim", "no_experience_hype", "email_is_free",
              "website_missing", "messaging_only", "no_interview"]:
        assert r[c] == 1, c
    assert r["domain_mismatch"] == 0  # free mail never counts as a mismatch
    assert r["urgency_hits"] >= 2


def test_binary_features_on_legit_listing():
    r = F.build_row(GOOD)
    for c in ["has_upfront_fee", "asks_personal_data", "guaranteed_claim", "no_experience_hype", "email_is_free",
              "website_missing", "domain_mismatch", "messaging_only", "no_interview", "vague_desc", "vague_requirements"]:
        assert r[c] == 0, c
    assert r["email_present"] == 1 and r["phone_present"] == 1
    assert r["interview_mode"] == "video_call" and r["employment_type"] == "full_time"


@pytest.mark.parametrize("email,site,mismatch", [
    ("careers@nexora.com", "https://nexora.com", 0),
    ("careers@nexora.com", "https://www.nexora.com/jobs?x=1", 0),
    ("careers@nexora-jobs.in", "https://nexora.com", 1),
    ("hr@other.com", "http://nexora.com", 1),
    ("careers@nexora.com", None, 0),
    ("careers@nexora.com", "", 0),
    ("hr@gmail.com", "https://nexora.com", 0),
    (None, "https://nexora.com", 0),
])
def test_domain_mismatch(email, site, mismatch):
    r = row(contact_email=email, company_website=site)
    assert r["domain_mismatch"] == mismatch
    assert r["website_missing"] == int(not site)


def test_vague_flags_use_word_thresholds():
    assert row(description="word " * 39)["vague_desc"] == 1
    assert row(description="word " * 40)["vague_desc"] == 0
    assert row(requirements="one two three four five six seven")["vague_requirements"] == 1  # 7 words
    assert row(requirements="one two three four five six seven eight")["vague_requirements"] == 0  # 8 words
    assert row(requirements=None)["vague_requirements"] == 1 and row(requirements=None)["req_words"] == 0


def test_no_experience_hype_needs_high_pay():
    text = "No experience needed for this role, we train you. " + "word " * 40
    assert row(description=text, salary_max=9000)["no_experience_hype"] == 0
    assert row(description=text, salary_max=90000)["no_experience_hype"] == 1


# ---------------------------------------------------------------- text_of
def test_text_of_is_lowercase_collapsed_and_ordered():
    t = F.text_of({"title": "Data  Intern", "company_name": "NEXORA\nLabs", "description": "Line one.\n\n  Line TWO",
                   "requirements": "Python"})
    assert t == "data intern nexora labs line one. line two python"
    assert F.text_of({"title": None, "company_name": "", "description": "x"}) == "x"
    long = F.text_of({"title": "t", "company_name": "c", "description": "a" * 9000})
    assert len(long) < 8100  # description truncated to 8000 chars


# ---------------------------------------------------------------- missing / empty inputs
def test_missing_and_empty_inputs_do_not_raise():
    for listing in ({}, {"title": None}, {k: "" for k in ["title", "company_name", "description", "requirements",
                    "location", "salary_min", "salary_max", "contact_email", "contact_phone", "company_website",
                    "upfront_fee_amount", "work_mode", "employment_type", "application_channel", "interview_mode",
                    "pay_period"]}, SimpleNamespace(), SimpleNamespace(title="t", description=None)):
        r = F.build_row(listing)
        assert list(r.keys()) == F.FEATURE_ORDER
        assert all(math.isfinite(r[c]) for c in F.NUM_COLS)
        assert r["vague_desc"] == 1 and r["vague_requirements"] == 1 and r["website_missing"] == 1
        assert r["email_present"] == 0 and r["phone_present"] == 0 and r["has_upfront_fee"] == 0
        assert (r["work_mode"], r["employment_type"], r["application_channel"], r["interview_mode"]) == \
            ("onsite", "internship", "unknown", "none")
        assert F.text_of(listing) in ("", "t")  # SimpleNamespace(title="t") is the only non-blank case


def test_csv_style_string_values_and_invalid_enums_fall_back():
    r = F.build_row({**BASE, "salary_min": "0", "salary_max": "0", "upfront_fee_amount": "1,499", "work_mode": "office",
                     "interview_mode": "zoom", "pay_period": "weekly", "salary_max_x": "junk"})
    assert r["salary_max_month_log"] == 0 and r["fee_amount_log"] == pytest.approx(math.log1p(1499))
    assert r["work_mode"] == "onsite" and r["interview_mode"] == "none"
    assert F.build_row({**BASE, "salary_max": "abc", "upfront_fee_amount": "-5"})["salary_max_month_log"] == 0


def test_accepts_pydantic_listing_input_if_available():
    schemas = pytest.importorskip("pydantic") and pytest.importorskip("app.schemas.ml_schemas")
    li = schemas.ListingInput(**{**RISKY, "company_website": None})
    assert dict(F.build_row(li)) == dict(F.build_row({**RISKY, "company_website": None}))


# ---------------------------------------------------------------- runtime constraints / data files
def test_runtime_path_does_not_import_pandas_numpy_sklearn():
    code = "import sys; import app.ml.features, app.ml.entities; " \
           "bad=[m for m in ('pandas','numpy','sklearn','scipy','pydantic') if m in sys.modules]; " \
           "sys.exit(1 if bad else 0)"
    env = {"PYTHONPATH": str(ROOT / "backend"), "PATH": "/usr/bin:/bin"}
    res = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr


def test_runtime_json_files_are_in_sync_with_lexicons_py():
    import lexicons as L
    assert json.loads((DATA / "role_benchmarks.json").read_text(encoding="utf-8")) == L.role_benchmarks_payload()
    assert json.loads((DATA / "lexicons_runtime.json").read_text(encoding="utf-8")) == L.RUNTIME_LEXICONS


def test_role_benchmarks_are_labelled_synthetic():
    data = json.loads((DATA / "role_benchmarks.json").read_text(encoding="utf-8"))
    assert data["_meta"]["data_type"] == "synthetic"
    assert "not verified" in data["_meta"]["notice"].lower()
    assert set(data["default"]) == set(F.CAT_VALUES["employment_type"])
    for r in data["roles"]:
        assert set(r["monthly_median_inr"]) == set(F.CAT_VALUES["employment_type"]) and r["keywords"]
    assert F.FREE_MAIL_DOMAINS is FREE_MAIL_DOMAINS
