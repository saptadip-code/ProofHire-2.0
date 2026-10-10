"""A-G2 dataset tests (Member 1). Run: pytest ml/tests -q

Deterministic: everything is derived from seed 42. Covers size, seed reproducibility, label balance, split
integrity / leakage, the six patterns, subtle + messy rows, label noise, blank handling and pattern signatures.
"""
import re
import tempfile
from collections import Counter
from functools import lru_cache
from pathlib import Path

import pytest

import generate_synthetic as G
import lexicons as L
from app.ml import features as F
from app.ml.entities import FREE_MAIL_DOMAINS

ROOT = Path(__file__).resolve().parents[2]
CSV = ROOT / "ml" / "data" / "listings_synthetic.csv"


@lru_cache(maxsize=None)
def rows(n=6000, ratio=0.38, seed=42):
    return tuple(tuple(r.items()) for r in G.generate_rows(n, ratio, seed))


def ds(**kw):
    return [dict(r) for r in rows(**kw)]


@lru_cache(maxsize=None)
def feats():
    return [(r, F.build_row(r)) for r in ds()]


def share(items, pred):
    items = list(items)
    return sum(1 for x in items if pred(x)) / len(items)


# ------------------------------------------------------------------ size / schema
def test_dataset_size_and_columns():
    d = ds()
    assert len(d) == 6000
    assert list(d[0].keys()) != [] and set(G.COLUMNS) <= set(d[0].keys())
    assert G.COLUMNS == ["listing_id", "title", "company_name", "description", "requirements", "location", "work_mode",
                         "employment_type", "salary_min", "salary_max", "pay_period", "contact_email", "contact_phone",
                         "application_channel", "company_website", "upfront_fee_amount", "interview_mode",
                         "scam_pattern", "difficulty", "label", "split"]
    assert [r["listing_id"] for r in d[:2]] == ["SYN-000001", "SYN-000002"] and d[-1]["listing_id"] == "SYN-006000"


def test_committed_csv_matches_regeneration():
    if not CSV.exists():
        pytest.skip("ml/data/listings_synthetic.csv not generated yet")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "regen.csv"
        G.write_csv(G.generate_rows(6000, 0.38, 42), out)
        assert CSV.read_bytes() == out.read_bytes(), "CSV was edited by hand or the generator changed; re-run it"
    header = CSV.read_text(encoding="utf-8").splitlines()[0]
    assert header == ",".join(G.COLUMNS)


# ------------------------------------------------------------------ seed reproducibility
def test_same_seed_is_identical_and_different_seed_differs():
    a = G.generate_rows(400, 0.38, 7)
    b = G.generate_rows(400, 0.38, 7)
    c = G.generate_rows(400, 0.38, 8)
    assert a == b
    assert a != c
    with tempfile.TemporaryDirectory() as tmp:
        pa, pb = Path(tmp) / "a.csv", Path(tmp) / "b.csv"
        G.write_csv(a, pa)
        G.write_csv(b, pb)
        assert G.csv_sha256(pa) == G.csv_sha256(pb)


def test_small_n_still_works():
    r = G.generate_rows(100, 0.38, 1)
    assert len(r) == 100 and Counter(x["split"] for x in r)["holdout"] == Counter(x["scam_pattern"] for x in r)["fake_offer_letter"]


# ------------------------------------------------------------------ label balance / patterns / noise
def test_label_balance_and_label_noise():
    d = ds()
    pre_noise_risky = sum(1 for r in d if r["scam_pattern"] != "legit")
    assert pre_noise_risky == 2280  # round(6000 * 0.38)
    noise = sum(1 for r in d if (r["label"] == 1) != (r["scam_pattern"] != "legit"))
    assert noise == 120  # exactly 2% of 6000 flipped
    risky_share = sum(r["label"] for r in d) / len(d)
    assert 0.37 <= risky_share <= 0.40
    assert set(r["label"] for r in d) == {0, 1}


def test_risky_pattern_mix_is_exact():
    c = Counter(r["scam_pattern"] for r in ds())
    assert c["legit"] == 3720
    assert (c["advance_fee"], c["unrealistic_pay"], c["data_harvest"], c["ghost_company"], c["mlm_pyramid"],
            c["fake_offer_letter"]) == (684, 456, 342, 342, 228, 228)
    assert set(c) == set(G.SCAM_PATTERNS)


def test_subtle_and_messy_counts():
    d = ds()
    subtle = [r for r in d if r["difficulty"] == "subtle"]
    messy = [r for r in d if r["difficulty"] == "messy"]
    assert len(subtle) == 342 and all(r["scam_pattern"] != "legit" for r in subtle)  # 15% of 2280
    assert len(messy) == 372 and all(r["scam_pattern"] == "legit" for r in messy)  # 10% of 3720
    assert {r["difficulty"] for r in d} == {"easy", "subtle", "messy"}


# ------------------------------------------------------------------ split integrity / leakage
def test_split_values_and_counts():
    d = ds()
    c = Counter(r["split"] for r in d)
    assert set(c) == {"train", "val", "test", "holdout"}
    assert c["holdout"] == 228 and sum(c.values()) == 6000
    assert abs(c["train"] / 5772 - 0.70) < 0.01 and abs(c["val"] / 5772 - 0.15) < 0.01 and abs(c["test"] / 5772 - 0.15) < 0.01


def test_split_is_stratified_by_scam_pattern():
    d = ds()
    for pattern in G.SCAM_PATTERNS:
        if pattern == "fake_offer_letter":
            continue
        grp = [r for r in d if r["scam_pattern"] == pattern]
        c = Counter(r["split"] for r in grp)
        n = len(grp)
        assert abs(c["train"] - 0.70 * n) <= 1 and abs(c["val"] - 0.15 * n) <= 1.5 and abs(c["test"] - 0.15 * n) <= 1.5, pattern
        assert c["holdout"] == 0


def test_fake_offer_letter_only_in_holdout():
    d = ds()
    for r in d:
        assert (r["scam_pattern"] == "fake_offer_letter") == (r["split"] == "holdout")
    assert not any(r["scam_pattern"] == "fake_offer_letter" for r in d if r["split"] in ("train", "val", "test"))


def test_no_duplicate_ids_or_listings_and_no_cross_split_leakage():
    d = ds()
    assert len({r["listing_id"] for r in d}) == 6000
    keys = [(r["company_name"], r["title"], r["description"]) for r in d]
    assert len(set(keys)) == 6000  # no exact duplicate listing anywhere -> none across splits
    desc_splits = {}
    for r in d:
        desc_splits.setdefault(r["description"], set()).add(r["split"])
    assert all(len(s) == 1 for s in desc_splits.values())


# ------------------------------------------------------------------ column value contracts
def test_enum_columns_use_guidebook_literals():
    for r in ds():
        assert r["work_mode"] in F.CAT_VALUES["work_mode"]
        assert r["employment_type"] in F.CAT_VALUES["employment_type"]
        assert r["application_channel"] in F.CAT_VALUES["application_channel"]
        assert r["interview_mode"] in F.CAT_VALUES["interview_mode"]
        assert r["pay_period"] in ("month", "year")
        assert r["location"] in L.LOCATIONS + [""]


def test_pay_period_mix_is_about_95_5():
    d = ds()
    assert 0.93 <= share(d, lambda r: r["pay_period"] == "month") <= 0.97


def test_numeric_and_length_constraints():
    for r in ds():
        assert isinstance(r["salary_min"], int) and isinstance(r["salary_max"], int)
        assert 0 <= r["salary_min"] <= r["salary_max"]
        assert (r["salary_min"] == 0) == (r["salary_max"] == 0)
        assert isinstance(r["upfront_fee_amount"], int) and r["upfront_fee_amount"] >= 0
        assert 50 <= len(r["description"].split()) <= 250
        assert len(r["requirements"].split()) <= 80
        assert 3 <= len(r["title"]) <= 200 and 2 <= len(r["company_name"]) <= 200 and len(r["description"]) <= 8000


def test_fee_values_by_pattern():
    d = ds()
    assert all(r["upfront_fee_amount"] == 0 for r in d if r["scam_pattern"] == "legit")
    af = [r for r in d if r["scam_pattern"] == "advance_fee" and r["difficulty"] == "easy"]
    assert all(499 <= r["upfront_fee_amount"] <= 9999 for r in af)
    assert all(r["upfront_fee_amount"] == 0 for r in d if r["difficulty"] == "subtle")


def test_blank_optional_fields_are_empty_strings():
    d = ds()
    assert any(r["requirements"] == "" for r in d) and any(r["company_website"] == "" for r in d)
    assert any(r["contact_phone"] == "" for r in d) and any(r["contact_email"] == "" for r in d)
    assert all(isinstance(r[c], str) for r in d for c in ("requirements", "contact_email", "contact_phone", "company_website", "location"))


def test_fictional_company_names_only():
    prefixes = set(L.COMPANY_PREFIXES)
    for r in ds():
        assert r["company_name"].split(" ", 1)[0] in prefixes


def test_phone_and_email_formats():
    for r in ds():
        if r["contact_phone"]:
            assert re.fullmatch(r"(\+91 )?[6-9]\d{9}", r["contact_phone"])
        if r["contact_email"]:
            assert re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", r["contact_email"])
        if r["company_website"]:
            assert r["company_website"].startswith("https://")


# ------------------------------------------------------------------ generation rules (A3)
def test_risky_rows_oversample_messaging_and_no_interview():
    d = ds()
    risky = [r for r in d if r["scam_pattern"] not in ("legit",) and r["difficulty"] == "easy"]
    legit = [r for r in d if r["scam_pattern"] == "legit"]
    assert share(risky, lambda r: r["application_channel"] in ("whatsapp", "telegram")) > 0.5
    assert share(legit, lambda r: r["application_channel"] in ("whatsapp", "telegram")) < 0.06
    assert share(risky, lambda r: r["interview_mode"] in ("none", "chat_only")) > 0.65
    assert share(legit, lambda r: r["interview_mode"] in ("none", "chat_only")) < 0.15


def test_requirements_empty_share_and_website_empty_share_for_risky():
    strong = [r for r in ds() if r["scam_pattern"] != "legit" and r["difficulty"] != "subtle"]
    assert 0.18 <= share(strong, lambda r: r["requirements"] == "") <= 0.32  # ~25%
    assert 0.45 <= share(strong, lambda r: r["company_website"] == "") <= 0.68  # ~55%


def test_legit_rows_have_corporate_email_matching_website_unless_messy():
    for r in ds():
        if r["scam_pattern"] == "legit" and r["difficulty"] == "easy" and r["contact_email"] and r["company_website"]:
            e = r["contact_email"].split("@")[1]
            assert e == r["company_website"].split("//")[1], r["listing_id"]
            assert e not in FREE_MAIL_DOMAINS


def test_messy_legit_rows_are_small_startups():
    messy = [r for r in ds() if r["difficulty"] == "messy"]
    assert share(messy, lambda r: r["contact_email"].split("@")[-1] in FREE_MAIL_DOMAINS) > 0.8
    assert share(messy, lambda r: r["company_website"] == "") > 0.8


def test_legit_salary_tracks_synthetic_benchmark():
    ratios = sorted(f["salary_ratio_vs_role"] for r, f in feats() if r["scam_pattern"] == "legit" and f["salary_ratio_vs_role"] > 0)
    median = ratios[len(ratios) // 2]
    assert 0.85 <= median <= 1.15  # lognormal(0, 0.35) around the benchmark median
    assert share(ratios, lambda x: x >= 3) < 0.01


def test_titles_resolve_to_a_benchmark_role():
    d = ds()
    assert share(d, lambda r: F.detect_role(r["title"]) != "default") > 0.99


# ------------------------------------------------------------------ pattern signatures through features
def _group(pattern, difficulty="easy"):
    return [f for r, f in feats() if r["scam_pattern"] == pattern and r["difficulty"] == difficulty]


def test_advance_fee_signature():
    g = _group("advance_fee")
    assert share(g, lambda f: f["has_upfront_fee"] == 1) == 1.0
    assert share(g, lambda f: f["messaging_only"] == 1) > 0.5


def test_unrealistic_pay_signature():
    g = _group("unrealistic_pay")
    assert share(g, lambda f: f["salary_ratio_vs_role"] >= 3) > 0.95
    assert share(g, lambda f: f["no_experience_hype"] == 1) > 0.65


def test_data_harvest_signature():
    g = _group("data_harvest")
    assert share(g, lambda f: f["asks_personal_data"] == 1) == 1.0
    assert share(g, lambda f: f["has_upfront_fee"] == 1) == 0.0


def test_ghost_company_signature():
    g = _group("ghost_company")
    assert share(g, lambda f: f["website_missing"] == 1) > 0.8
    assert share(g, lambda f: f["has_upfront_fee"] == 1) == 0.0
    assert share(g, lambda f: f["vague_requirements"] == 1) > 0.6


def test_mlm_signature():
    g = _group("mlm_pyramid")
    assert 0.35 <= share(g, lambda f: f["has_upfront_fee"] == 1) <= 0.7  # joining / starter kit


def test_fake_offer_letter_signature():
    g = _group("fake_offer_letter")
    assert share(g, lambda f: f["no_interview"] == 1) > 0.7
    assert share(g, lambda f: f["has_upfront_fee"] == 1) > 0.5


def test_legit_rows_do_not_trigger_strong_risk_features():
    for r, f in feats():
        if r["scam_pattern"] == "legit":
            assert f["has_upfront_fee"] == 0 and f["asks_personal_data"] == 0 and f["guaranteed_claim"] == 0, r["listing_id"]
            assert f["urgency_hits"] < 2 and f["exclaim_count"] < 4 and f["caps_ratio"] <= 0.25, r["listing_id"]
    legit = [f for r, f in feats() if r["scam_pattern"] == "legit" and r["difficulty"] == "easy"]
    assert share(legit, lambda f: f["req_words"] >= 25) > 0.85  # DETAILED_REQUIREMENTS territory


def test_subtle_rows_have_one_or_two_weak_signals_and_no_strong_ones():
    for r, f in feats():
        if r["difficulty"] == "subtle":
            assert f["has_upfront_fee"] == 0 and f["asks_personal_data"] == 0 and f["guaranteed_claim"] == 0
            assert f["exclaim_count"] == 0
    sub = [f for r, f in feats() if r["difficulty"] == "subtle"]
    weak_cols = ["email_is_free", "website_missing", "domain_mismatch", "messaging_only", "no_interview",
                 "vague_requirements"]
    n_weak = [sum(f[c] for c in weak_cols) + int(f["salary_ratio_vs_role"] > 1.7) + int(f["urgency_hits"] >= 1) for f in sub]
    assert share(n_weak, lambda k: k >= 1) > 0.9
    assert max(n_weak) <= 6


def test_every_row_featurises_with_in_range_values():
    for r, f in feats():
        assert 0 <= f["salary_ratio_vs_role"] <= 20 and 0 <= f["salary_spread"] <= 10 and 0 <= f["exclaim_count"] <= 15
        assert 0 <= f["caps_ratio"] <= 1
    assert F.FEATURE_ORDER == list(feats()[0][1].keys())
