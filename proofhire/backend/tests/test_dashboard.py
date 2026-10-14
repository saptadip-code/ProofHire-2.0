"""Phase 6: GET /dashboard/summary, /dashboard/trends, /dashboard/model-metrics
(guidebook Section 5.4 and B4).

Rows are inserted straight into the in-memory SQLite database so every expected number is exact.
The dashboard reads the database only; no ML code is involved. For the metrics endpoint the tests
point the service at a temporary folder holding TEST FIXTURE files (made-up numbers that exist only
inside the tests, never in the project) so the file handling can be checked.
"""

from __future__ import annotations

import copy
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from app.db.models import (
    Assessment,
    EntitySignal,
    EvidenceItem,
    Listing,
    LlmCall,
    Report,
)
from app.services import dashboard_service
from tests.test_assessments_api import assert_error, bearer

SUMMARY = "/api/v1/dashboard/summary"
TRENDS = "/api/v1/dashboard/trends"
METRICS = "/api/v1/dashboard/model-metrics"

TODAY = date(2026, 10, 12)  # the fixed "today" for every test in this file

SUMMARY_KEYS = {
    "total_assessments", "by_level", "avg_risk_score", "top_evidence", "reports",
    "connections_found", "llm", "data_scope",
}


# ------------------------------------------------------------------ fixtures
@pytest.fixture(autouse=True)
def fixed_today_and_clean_cache(monkeypatch):
    """The in-memory cache lives for the whole process, so clear it around every test; fix 'today'."""
    dashboard_service.clear_cache()
    monkeypatch.setattr(dashboard_service, "_today", lambda: TODAY)
    yield
    dashboard_service.clear_cache()


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture()
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(dashboard_service, "_clock", c)
    return c


def add_assessment(
    db_factory,
    *,
    level="low",
    score=0.1,
    demo=False,
    source="llm",
    created=None,
    evidence=(),
    signals=(),
    reports=(),
    llm_calls=(),
) -> int:
    """Insert one listing + assessment (+ evidence/signals/reports/llm_calls). Returns the assessment id.

    evidence: (code, label) tuples; signals: (signal_type, signal_value); reports: status strings;
    llm_calls: (provider, success, latency_ms).
    """
    created = created or datetime(2026, 10, 12, 9, 0, 0)
    with db_factory() as db:
        listing = Listing(
            title="Test listing", company_name="Nexora Labs", description="d" * 30,
            is_synthetic_demo=demo, created_at=created,
        )
        db.add(listing)
        db.flush()
        a = Assessment(
            listing_id=listing.id, risk_score=score, risk_level=level, threshold_low=0.35, threshold_high=0.7,
            model_version="test-model", explanation_source=source, summary="s", key_concerns=[], what_to_verify=[],
            created_at=created,
        )
        db.add(a)
        db.flush()
        for i, (code, label) in enumerate(evidence, start=1):
            db.add(EvidenceItem(
                assessment_id=a.id, public_id=f"E{i}", code=code, label=label, evidence_type="observed",
                direction="increases_risk", severity=2, sort_order=i,
            ))
        for st, sv in signals:
            db.add(EntitySignal(assessment_id=a.id, signal_type=st, signal_value=sv))
        for i, status in enumerate(reports):
            db.add(Report(
                assessment_id=a.id, reporter_key=f"key{a.id}-{i}", report_type="other",
                description="x" * 20, status=status,
            ))
        for provider, ok, latency in llm_calls:
            db.add(LlmCall(assessment_id=a.id, provider=provider, model="m", latency_ms=latency, success=ok))
        db.commit()
        return a.id


def summary(api, **params):
    r = api.get(SUMMARY, params=params)
    assert r.status_code == 200, r.text
    return r.json()


# ====================================================== GET /dashboard/summary
def test_empty_database_gives_zero_counts_and_null_averages_not_made_up_numbers(api):
    body = summary(api)
    assert set(body) == SUMMARY_KEYS
    assert body["total_assessments"] == 0
    assert body["by_level"] == {"low": 0, "medium": 0, "high": 0}
    assert body["avg_risk_score"] is None
    assert body["top_evidence"] == []
    assert body["reports"] == {"total": 0, "pending": 0, "approved": 0, "rejected": 0}
    assert body["connections_found"] == 0
    assert body["llm"] == {"calls": 0, "success_rate": None, "avg_latency_ms": None, "template_fallbacks": 0}
    assert body["data_scope"] == "real_only"


def test_totals_levels_and_average_score(api, db_factory):
    add_assessment(db_factory, level="low", score=0.10)
    add_assessment(db_factory, level="high", score=0.90)
    add_assessment(db_factory, level="high", score=0.70)
    add_assessment(db_factory, level="medium", score=0.50)
    body = summary(api)
    assert body["total_assessments"] == 4
    assert body["by_level"] == {"low": 1, "medium": 1, "high": 2}
    assert body["avg_risk_score"] == pytest.approx(0.55, abs=1e-4)  # (0.1 + 0.9 + 0.7 + 0.5) / 4


def test_summary_needs_no_login_and_ignores_an_authorization_header(api):
    assert api.get(SUMMARY).status_code == 200
    assert api.get(SUMMARY, headers=bearer("garbage")).status_code == 200  # public: no auth dependency


# ------------------------------------------------------------ demo exclusion
def test_demo_rows_are_excluded_by_default(api, db_factory):
    add_assessment(db_factory, level="low", score=0.2)
    add_assessment(db_factory, level="high", score=0.9, demo=True)
    for params in ({}, {"include_demo": "false"}):
        body = summary(api, **params)
        assert body["total_assessments"] == 1 and body["by_level"]["high"] == 0
        assert body["avg_risk_score"] == pytest.approx(0.2, abs=1e-4)
        assert body["data_scope"] == "real_only"
        dashboard_service.clear_cache()


def test_include_demo_true_counts_demo_rows_and_says_so(api, db_factory):
    add_assessment(db_factory, level="low", score=0.2)
    add_assessment(db_factory, level="high", score=0.8, demo=True)
    body = summary(api, include_demo="true")
    assert body["total_assessments"] == 2 and body["by_level"] == {"low": 1, "medium": 0, "high": 1}
    assert body["avg_risk_score"] == pytest.approx(0.5, abs=1e-4)
    assert body["data_scope"] == "including_demo"


def test_demo_data_is_excluded_from_every_section_by_default(api, db_factory):
    add_assessment(
        db_factory, level="high", score=0.9, demo=True, source="template",
        evidence=[("UPFRONT_FEE", "Asks the applicant to pay money")],
        signals=[("email", "scam@gmail.com")], reports=["approved", "pending"],
        llm_calls=[("groq", True, 500)],
    )
    add_assessment(db_factory, level="high", score=0.9, demo=True, signals=[("email", "scam@gmail.com")])
    body = summary(api)
    assert body["total_assessments"] == 0 and body["top_evidence"] == []
    assert body["reports"]["total"] == 0 and body["connections_found"] == 0
    assert body["llm"] == {"calls": 0, "success_rate": None, "avg_latency_ms": None, "template_fallbacks": 0}
    # ... and they all appear when asked for.
    body = summary(api, include_demo="true")
    assert body["total_assessments"] == 2 and body["top_evidence"][0]["count"] == 1
    assert body["reports"] == {"total": 2, "pending": 1, "approved": 1, "rejected": 0}
    assert body["connections_found"] == 1
    assert body["llm"]["calls"] == 1 and body["llm"]["template_fallbacks"] == 1


@pytest.mark.parametrize("value", ["maybe", "2"])
def test_include_demo_must_be_a_boolean(api, value):
    assert_error(api.get(SUMMARY, params={"include_demo": value}), 422, "validation_error")


@pytest.mark.parametrize("value", ["true", "1", "True"])
def test_include_demo_accepts_boolean_spellings(api, db_factory, value):
    add_assessment(db_factory, demo=True)
    assert summary(api, include_demo=value)["total_assessments"] == 1
    dashboard_service.clear_cache()


# ---------------------------------------------------------------- top_evidence
def test_top_evidence_counts_orders_and_labels(api, db_factory):
    fee = ("UPFRONT_FEE", "Asks the applicant to pay money")
    free = ("FREE_EMAIL_CONTACT", "A free e-mail address is the company contact")
    vague = ("VAGUE_DESCRIPTION", "The description is very short")
    add_assessment(db_factory, evidence=[fee, free])
    add_assessment(db_factory, evidence=[fee, vague])
    add_assessment(db_factory, evidence=[fee])
    add_assessment(db_factory, evidence=[free])
    top = summary(api)["top_evidence"]
    assert top == [
        {"code": "UPFRONT_FEE", "label": fee[1], "count": 3},
        {"code": "FREE_EMAIL_CONTACT", "label": free[1], "count": 2},
        {"code": "VAGUE_DESCRIPTION", "label": vague[1], "count": 1},
    ]


def test_top_evidence_is_limited_to_8_and_ties_are_ordered_by_code(api, db_factory):
    add_assessment(db_factory, evidence=[(f"CODE_{c}", f"label {c}") for c in "JIHGFEDCBA"])
    top = summary(api)["top_evidence"]
    assert len(top) == 8
    assert [t["code"] for t in top] == [f"CODE_{c}" for c in "ABCDEFGH"]


def test_model_terms_with_different_labels_are_counted_separately(api, db_factory):
    """MODEL_TERM labels carry the term, so each wording is its own bar (never merged into one fake label)."""
    a = ("MODEL_TERM", "Wording often seen in risky listings: 'guaranteed placement'")
    b = ("MODEL_TERM", "Wording often seen in risky listings: 'limited seats'")
    add_assessment(db_factory, evidence=[a])
    add_assessment(db_factory, evidence=[a, b])
    top = summary(api)["top_evidence"]
    assert top[0] == {"code": "MODEL_TERM", "label": a[1], "count": 2}
    assert top[1] == {"code": "MODEL_TERM", "label": b[1], "count": 1}


# --------------------------------------------------------------------- reports
def test_report_counts_by_status(api, db_factory):
    add_assessment(db_factory, reports=["pending", "pending", "approved"])
    add_assessment(db_factory, reports=["rejected", "approved"])
    add_assessment(db_factory)
    assert summary(api)["reports"] == {"total": 5, "pending": 2, "approved": 2, "rejected": 1}


def test_report_counts_follow_moderation_through_the_real_api(api, ml, db_factory):
    """End to end: a report made and approved through the API shows up in the dashboard counts."""
    from tests.test_assessments_api import RISKY, create
    from tests.test_reports import ADMIN, make_admin, report

    aid = create(api, RISKY).json()["assessment_id"]
    rid = report(api, aid).json()["id"]
    assert summary(api)["reports"] == {"total": 1, "pending": 1, "approved": 0, "rejected": 0}
    admin = make_admin(api, db_factory)
    assert api.patch(f"{ADMIN}/{rid}", json={"status": "approved"}, headers=bearer(admin)).status_code == 200
    dashboard_service.clear_cache()  # the summary is cached for 30 s
    assert summary(api)["reports"] == {"total": 1, "pending": 0, "approved": 1, "rejected": 0}


# ----------------------------------------------------------- connections_found
def test_connections_found_counts_repeated_signals_across_different_assessments(api, db_factory):
    add_assessment(db_factory, signals=[("email", "x@gmail.com"), ("phone", "9876543210"), ("company_name", "acme")])
    add_assessment(db_factory, signals=[("email", "x@gmail.com"), ("company_name", "acme")])
    add_assessment(db_factory, signals=[("email", "x@gmail.com"), ("phone", "1111111111")])
    # x@gmail.com (3 assessments) and "acme" (2) are connections; the two phones are not.
    assert summary(api)["connections_found"] == 2


def test_same_value_twice_in_one_assessment_is_not_a_connection(api, db_factory):
    add_assessment(db_factory, signals=[("email", "x@gmail.com"), ("email", "x@gmail.com")])
    assert summary(api)["connections_found"] == 0


def test_same_value_with_a_different_signal_type_is_not_a_connection(api, db_factory):
    add_assessment(db_factory, signals=[("email_domain", "acme.com")])
    add_assessment(db_factory, signals=[("website_domain", "acme.com")])
    assert summary(api)["connections_found"] == 0


def test_a_connection_through_a_demo_row_only_counts_with_include_demo(api, db_factory):
    add_assessment(db_factory, signals=[("email", "x@gmail.com")])
    add_assessment(db_factory, signals=[("email", "x@gmail.com")], demo=True)
    assert summary(api)["connections_found"] == 0
    assert summary(api, include_demo="true")["connections_found"] == 1


# ------------------------------------------------------------------------ llm
def test_llm_stats_count_real_calls_only(api, db_factory):
    add_assessment(db_factory, source="llm", llm_calls=[("groq", True, 1000), ("groq", True, 2000)])
    add_assessment(db_factory, source="template", llm_calls=[("groq", False, 3000), ("template", True, 0)])
    add_assessment(db_factory, source="template", llm_calls=[("template", True, 0)])
    llm = summary(api)["llm"]
    assert llm["calls"] == 3  # the two 'template' rows are the built-in fallback, not LLM calls
    assert llm["success_rate"] == pytest.approx(2 / 3, abs=1e-4)
    assert llm["avg_latency_ms"] == pytest.approx(2000.0)
    assert llm["template_fallbacks"] == 2  # assessments whose explanation came from the template


def test_llm_calls_of_deleted_assessments_are_kept_in_the_statistics(api, db_factory):
    aid = add_assessment(db_factory, llm_calls=[("groq", True, 400)])
    with db_factory() as db:  # what DELETE /assessments does to the log: assessment_id -> NULL
        db.query(LlmCall).update({LlmCall.assessment_id: None})
        db.query(Report).delete()
        db.query(Assessment).filter(Assessment.id == aid).delete()
        db.commit()
    llm = summary(api)["llm"]
    assert llm["calls"] == 1 and llm["success_rate"] == 1.0 and llm["avg_latency_ms"] == 400.0


# ---------------------------------------------------------------------- cache
def test_summary_is_cached_for_30_seconds_then_recomputed(api, db_factory, clock):
    add_assessment(db_factory)
    assert summary(api)["total_assessments"] == 1
    add_assessment(db_factory)
    clock.now += 29
    assert summary(api)["total_assessments"] == 1  # still the cached answer
    clock.now += 2  # 31 s after the first call
    assert summary(api)["total_assessments"] == 2


def test_cache_key_includes_include_demo(api, db_factory, clock):
    add_assessment(db_factory)
    add_assessment(db_factory, demo=True)
    assert summary(api)["total_assessments"] == 1
    assert summary(api, include_demo="true")["total_assessments"] == 2  # not served from the real_only entry
    assert summary(api)["total_assessments"] == 1


# ===================================================== GET /dashboard/trends
def trends(api, **params):
    r = api.get(TRENDS, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def at(days_ago: int, hour=12, minute=0, second=0) -> datetime:
    d = TODAY - timedelta(days=days_ago)
    return datetime(d.year, d.month, d.day, hour, minute, second)


def test_default_is_14_zero_filled_days_oldest_first_ending_today(api):
    body = trends(api)
    assert len(body) == 14
    assert body[-1]["date"] == "2026-10-12" and body[0]["date"] == "2026-09-29"
    assert [p["date"] for p in body] == sorted(p["date"] for p in body)
    assert len({p["date"] for p in body}) == 14
    for p in body:
        assert set(p) == {"date", "count", "high", "medium", "low"}
        assert (p["count"], p["high"], p["medium"], p["low"]) == (0, 0, 0, 0)


def test_counts_are_grouped_by_day_and_level(api, db_factory):
    add_assessment(db_factory, level="high", created=at(0))
    add_assessment(db_factory, level="high", created=at(0, 1))
    add_assessment(db_factory, level="low", created=at(0, 23, 59, 59))
    add_assessment(db_factory, level="medium", created=at(2))
    add_assessment(db_factory, level="low", created=at(5))
    by_date = {p["date"]: p for p in trends(api)}
    assert by_date["2026-10-12"] == {"date": "2026-10-12", "count": 3, "high": 2, "medium": 0, "low": 1}
    assert by_date["2026-10-10"] == {"date": "2026-10-10", "count": 1, "high": 0, "medium": 1, "low": 0}
    assert by_date["2026-10-07"]["count"] == 1 and by_date["2026-10-07"]["low"] == 1
    assert by_date["2026-10-11"]["count"] == 0  # a day with no rows is present with zeros
    assert sum(p["count"] for p in by_date.values()) == 5


def test_range_boundaries_for_days_14(api, db_factory):
    """The window is the 14 calendar days ending today: 2026-09-29 .. 2026-10-12 (UTC)."""
    add_assessment(db_factory, created=at(13, 0, 0, 0))  # 2026-09-29 00:00:00 -> inside (first day)
    add_assessment(db_factory, created=at(14, 23, 59, 59))  # 2026-09-28 23:59:59 -> outside
    add_assessment(db_factory, created=at(0, 23, 59, 59))  # today 23:59:59 -> inside
    body = trends(api, days=14)
    assert body[0]["date"] == "2026-09-29" and body[0]["count"] == 1
    assert sum(p["count"] for p in body) == 2


def test_days_parameter_changes_the_window(api, db_factory):
    add_assessment(db_factory, created=at(0))
    add_assessment(db_factory, created=at(3))
    add_assessment(db_factory, created=at(40))
    one = trends(api, days=1)
    assert [p["date"] for p in one] == ["2026-10-12"] and one[0]["count"] == 1
    assert len(trends(api, days=7)) == 7 and sum(p["count"] for p in trends(api, days=7)) == 2
    sixty = trends(api, days=60)
    assert len(sixty) == 60 and sixty[0]["date"] == "2026-08-14" and sum(p["count"] for p in sixty) == 3


@pytest.mark.parametrize("days", ["0", "-3", "61", "abc", "1.5"])
def test_days_outside_1_to_60_or_not_an_integer_is_422(api, days):
    err = assert_error(api.get(TRENDS, params={"days": days}), 422, "validation_error")
    assert [f["field"] for f in err["fields"]] == ["days"]


def test_trends_exclude_demo_by_default_and_include_it_on_request(api, db_factory):
    add_assessment(db_factory, level="low", created=at(0))
    add_assessment(db_factory, level="high", created=at(0), demo=True)
    assert trends(api)[-1]["count"] == 1 and trends(api)[-1]["high"] == 0
    dashboard_service.clear_cache()
    assert trends(api, include_demo="false")[-1]["count"] == 1
    dashboard_service.clear_cache()
    both = trends(api, include_demo="true")[-1]
    assert both["count"] == 2 and both["high"] == 1 and both["low"] == 1


def test_trends_include_demo_must_be_a_boolean(api):
    assert_error(api.get(TRENDS, params={"include_demo": "maybe"}), 422, "validation_error")


def test_trends_is_public(api):
    assert api.get(TRENDS).status_code == 200
    assert api.get(TRENDS, headers=bearer("garbage")).status_code == 200


def test_trends_cache_lasts_60_seconds_and_is_keyed_by_days_and_demo(api, db_factory, clock):
    add_assessment(db_factory, created=at(0))
    assert trends(api)[-1]["count"] == 1
    add_assessment(db_factory, created=at(0))
    clock.now += 59
    assert trends(api)[-1]["count"] == 1  # cached
    assert trends(api, days=7)[-1]["count"] == 2  # different key: computed fresh
    clock.now += 2
    assert trends(api)[-1]["count"] == 2  # expired


def test_trends_after_midnight_move_the_window(api, db_factory, monkeypatch):
    add_assessment(db_factory, created=at(0))  # created on 2026-10-12
    monkeypatch.setattr(dashboard_service, "_today", lambda: TODAY + timedelta(days=1))
    dashboard_service.clear_cache()
    body = trends(api, days=2)
    assert [p["date"] for p in body] == ["2026-10-12", "2026-10-13"]
    assert [p["count"] for p in body] == [1, 0]


# ================================================= GET /dashboard/model-metrics
# TEST FIXTURE ONLY. These numbers exist to exercise the file handling; they are not model results.
FIXTURE_METRICS = {
    "synthetic_test": {
        "precision": 0.5, "recall": 0.25, "f1": 0.3333, "roc_auc": 0.6, "pr_auc": 0.4, "brier": 0.2,
        "confusion": [[10, 2], [3, 5]],
    },
    "baselines": {"M0": {"pr_auc": 0.1}, "M3": {"pr_auc": 0.4}},
    "pattern_holdout": {"recall": 0.2, "n": 7},
    "handwritten": {"precision": 0.3, "recall": 0.2, "n": 60},
    "cv": {"pr_auc_mean": 0.4, "pr_auc_std": 0.01},
    "limitations": ["Fixture limitation one.", "Fixture limitation two."],
}


@pytest.fixture()
def artifacts(tmp_path, monkeypatch) -> Path:
    """An empty artifacts folder; the service reads metrics.json and model_meta.json from it."""
    monkeypatch.setattr(dashboard_service, "METRICS_PATH", tmp_path / "metrics.json")
    monkeypatch.setattr(dashboard_service, "MODEL_META_PATH", tmp_path / "model_meta.json")
    return tmp_path


def write_metrics(folder: Path, data=FIXTURE_METRICS, *, raw: str | bytes | None = None) -> None:
    path = folder / "metrics.json"
    if raw is None:
        path.write_text(json.dumps(data), encoding="utf-8")
    elif isinstance(raw, bytes):
        path.write_bytes(raw)
    else:
        path.write_text(raw, encoding="utf-8")


def write_meta(folder: Path, version="fixture-version-1") -> None:
    (folder / "model_meta.json").write_text(json.dumps({"model_version": version}), encoding="utf-8")


def test_default_location_is_app_ml_artifacts_metrics_json():
    assert dashboard_service.METRICS_PATH.parts[-4:] == ("app", "ml", "artifacts", "metrics.json")
    assert dashboard_service.MODEL_META_PATH.parts[-4:] == ("app", "ml", "artifacts", "model_meta.json")


def test_valid_file_is_returned_unchanged_plus_model_version(api, artifacts):
    write_metrics(artifacts)
    write_meta(artifacts, "fixture-version-1")
    r = api.get(METRICS)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {**FIXTURE_METRICS, "model_version": "fixture-version-1"}
    assert r.headers["Cache-Control"] == "public, max-age=300"


def test_extra_keys_in_the_file_are_passed_through(api, artifacts):
    data = copy.deepcopy(FIXTURE_METRICS)
    data["extra_section"] = {"anything": [1, 2, 3]}
    data["synthetic_test"]["extra_metric"] = 0.9
    write_metrics(artifacts, data)
    write_meta(artifacts)
    body = api.get(METRICS).json()
    assert body["extra_section"] == {"anything": [1, 2, 3]} and body["synthetic_test"]["extra_metric"] == 0.9


def test_missing_model_meta_gives_null_model_version_but_real_metrics(api, artifacts):
    write_metrics(artifacts)
    r = api.get(METRICS)
    assert r.status_code == 200
    assert r.json()["model_version"] is None and r.json()["synthetic_test"] == FIXTURE_METRICS["synthetic_test"]


@pytest.mark.parametrize("meta_text", ["not json", "[]", '{"model_version": 5}', '{"model_version": ""}', "{}"])
def test_unusable_model_meta_gives_null_model_version(api, artifacts, meta_text):
    write_metrics(artifacts)
    (artifacts / "model_meta.json").write_text(meta_text, encoding="utf-8")
    r = api.get(METRICS)
    assert r.status_code == 200 and r.json()["model_version"] is None


def test_metrics_file_is_read_on_every_request_so_a_new_export_shows_up(api, artifacts):
    write_metrics(artifacts)
    assert api.get(METRICS).json()["synthetic_test"]["precision"] == 0.5
    changed = copy.deepcopy(FIXTURE_METRICS)
    changed["synthetic_test"]["precision"] = 0.75
    write_metrics(artifacts, changed)
    assert api.get(METRICS).json()["synthetic_test"]["precision"] == 0.75


def test_missing_metrics_file_is_503_and_nothing_is_substituted(api, artifacts):
    write_meta(artifacts)  # the model exists, its metrics do not
    r = api.get(METRICS)
    err = assert_error(r, 503, "model_unavailable")
    assert "metrics.json was not found" in err["message"] and err["fields"] == []
    assert set(r.json()) == {"error"}  # no metrics-looking fields at all
    assert "public" not in r.headers.get("Cache-Control", "")  # an error must not be cached


def test_real_project_without_ml_artifacts_gives_503(api):
    """Right now app/ml/artifacts/metrics.json does not exist in this project (ML teammate's file)."""
    if dashboard_service.METRICS_PATH.exists():
        pytest.skip("the AI/ML artifacts are installed in this checkout")
    assert_error(api.get(METRICS), 503, "model_unavailable")


@pytest.mark.parametrize(
    "raw, reason",
    [
        ("", "not valid JSON"),
        ("   \n", "not valid JSON"),
        ("{not json", "not valid JSON"),
        ('{"synthetic_test": {"precision": NaN}}', "not valid JSON"),
        ('{"synthetic_test": {"precision": Infinity}}', "not valid JSON"),
        (b"\xff\xfe\x00bad", "could not be read"),
        ("[]", "top level must be a JSON object"),
        ('"text"', "top level must be a JSON object"),
        ("null", "top level must be a JSON object"),
        ("{}", "missing key(s)"),
    ],
)
def test_unreadable_or_wrongly_shaped_files_are_503_with_a_reason(api, artifacts, raw, reason):
    write_metrics(artifacts, raw=raw)
    err = assert_error(api.get(METRICS), 503, "model_unavailable")
    assert reason in err["message"]


def _without(path: str):
    data = copy.deepcopy(FIXTURE_METRICS)
    node = data
    *parents, last = path.split(".")
    for p in parents:
        node = node[p]
    del node[last]
    return data


def _with(path: str, value):
    data = copy.deepcopy(FIXTURE_METRICS)
    node = data
    *parents, last = path.split(".")
    for p in parents:
        node = node[p]
    node[last] = value
    return data


@pytest.mark.parametrize(
    "data",
    [
        *[_without(k) for k in ("synthetic_test", "baselines", "pattern_holdout", "handwritten", "cv", "limitations")],
        *[_without(f"synthetic_test.{k}") for k in ("precision", "recall", "f1", "roc_auc", "pr_auc", "brier", "confusion")],
        _with("synthetic_test", []),
        _with("baselines", "x"),
        _with("limitations", "one string"),
        _with("limitations", [1, 2]),
        _with("synthetic_test.precision", "0.5"),
        _with("synthetic_test.recall", None),
        _with("synthetic_test.f1", True),
        _with("synthetic_test.confusion", [[1, 2, 3], [4, 5]]),
        _with("synthetic_test.confusion", [[1, 2]]),
        _with("synthetic_test.confusion", [["a", 2], [3, 4]]),
        _with("synthetic_test.confusion", "2x2"),
    ],
)
def test_files_that_miss_the_documented_structure_are_503(api, artifacts, data):
    write_metrics(artifacts, data)
    err = assert_error(api.get(METRICS), 503, "model_unavailable")
    assert "expected structure" in err["message"]


def test_oversized_file_is_503(api, artifacts, monkeypatch):
    write_metrics(artifacts)
    monkeypatch.setattr(dashboard_service, "MAX_ARTIFACT_BYTES", 10)
    err = assert_error(api.get(METRICS), 503, "model_unavailable")
    assert "too large" in err["message"]


def test_error_message_never_leaks_server_paths_or_file_content(api, artifacts):
    write_metrics(artifacts, raw='{"secret_field": "do-not-leak"}')
    r = api.get(METRICS)
    assert r.status_code == 503
    assert str(artifacts) not in r.text and "do-not-leak" not in r.text and "secret_field" not in r.text


def test_metrics_endpoint_is_public_and_read_only(api, artifacts):
    write_metrics(artifacts)
    before = (artifacts / "metrics.json").read_bytes()
    assert api.get(METRICS).status_code == 200
    assert api.get(METRICS, headers=bearer("garbage")).status_code == 200
    assert (artifacts / "metrics.json").read_bytes() == before  # the backend never writes the file
    assert api.post(METRICS, json={}).status_code == 405


# ----------------------------------------------------------------- earlier phases
def test_earlier_routes_are_still_in_the_openapi_document(api):
    paths = set(api.get("/openapi.json").json()["paths"])
    for p in (
        "/api/v1/health", "/api/v1/auth/login", "/api/v1/assessments", "/api/v1/assessments/compare",
        "/api/v1/reports", "/api/v1/reports/mine", "/api/v1/admin/reports", "/api/v1/admin/reports/{report_id}",
        "/api/v1/dashboard/summary", "/api/v1/dashboard/trends", "/api/v1/dashboard/model-metrics",
    ):
        assert p in paths, p
