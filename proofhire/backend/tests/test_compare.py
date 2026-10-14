"""POST /api/v1/assessments/compare (guidebook Section 5.4, B4).

Real app code, in-memory SQLite, TEST-ONLY fake ML package (see tests/ml_fakes.py).
In the fakes a listing with an upfront fee scores 0.91 "high" and one without scores
0.12 "low"; both carry the same two evidence items (one observed risk signal each).
"""

from __future__ import annotations

import pytest

from app.db.models import Report
from tests.test_assessments_api import BASE, RISKY, SAFE, assert_error, create

URL = f"{BASE}/compare"

SIGNALS = [
    "risk_score",
    "risk_level",
    "upfront_fee_amount",
    "salary_monthly",
    "email_type",
    "website_present",
    "interview_mode",
    "application_channel",
    "observed_risk_signals",
    "approved_reports",
    "connections_count",
]
SUMMARY_KEYS = {
    "id", "created_at", "title", "company_name", "risk_score", "risk_level", "evidence_count", "report_count_approved",
}


def compare(api, a, b):
    return api.post(URL, json={"assessment_id_a": a, "assessment_id_b": b})


def rows_by_signal(response) -> dict:
    return {row["signal"]: row for row in response.json()["rows"]}


@pytest.fixture()
def pair(api, ml):
    """(risky, safe) assessments, created anonymously."""
    return create(api, RISKY).json(), create(api, SAFE).json()


# ================================================================== contract shape
def test_response_has_exactly_a_b_and_rows(api, pair):
    r = compare(api, pair[0]["assessment_id"], pair[1]["assessment_id"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"a", "b", "rows"}
    assert set(body["a"]) == SUMMARY_KEYS and set(body["b"]) == SUMMARY_KEYS
    assert body["a"]["id"] == pair[0]["assessment_id"] and body["b"]["id"] == pair[1]["assessment_id"]
    assert body["a"]["title"] == RISKY["title"] and body["b"]["company_name"] == SAFE["company_name"]
    assert body["a"]["risk_level"] == "high" and body["b"]["risk_level"] == "low"
    assert body["a"]["evidence_count"] == 2
    assert [row["signal"] for row in body["rows"]] == SIGNALS
    assert all(set(row) == {"signal", "a", "b", "better"} for row in body["rows"])
    assert all(row["better"] in ("a", "b", "tie") for row in body["rows"])


def test_row_values_and_the_lower_risk_side_wins(api, pair):
    rows = rows_by_signal(compare(api, pair[0]["assessment_id"], pair[1]["assessment_id"]))
    expected = {
        "risk_score": (0.91, 0.12, "b"),
        "risk_level": ("high", "low", "b"),
        "upfront_fee_amount": (1499, 0, "b"),
        "salary_monthly": (40000, None, "tie"),  # no honest ordering for pay, so always a tie
        "email_type": ("free", "company", "b"),
        "website_present": (False, True, "b"),
        "interview_mode": ("chat_only", "video_call", "b"),
        "application_channel": ("whatsapp", "email", "b"),
        "observed_risk_signals": (1, 1, "tie"),
        "approved_reports": (0, 0, "tie"),
        "connections_count": (0, 0, "tie"),
    }
    for signal, (a_value, b_value, better) in expected.items():
        assert (rows[signal]["a"], rows[signal]["b"], rows[signal]["better"]) == (a_value, b_value, better), signal


def test_swapping_the_ids_swaps_the_winner(api, pair):
    rows = rows_by_signal(compare(api, pair[1]["assessment_id"], pair[0]["assessment_id"]))
    assert rows["risk_score"] == {"signal": "risk_score", "a": 0.12, "b": 0.91, "better": "a"}
    assert rows["email_type"]["better"] == "a"


def test_identical_listings_tie_everywhere(api, ml):
    first, second = create(api, SAFE).json(), create(api, SAFE).json()
    rows = compare(api, first["assessment_id"], second["assessment_id"]).json()["rows"]
    assert {row["better"] for row in rows} == {"tie"}


# ================================================================== individual rows
def test_yearly_pay_is_normalised_to_monthly_and_one_time_pay_is_null(api, ml):
    yearly = create(api, {**SAFE, "salary_min": 300000, "salary_max": 600000, "pay_period": "year"}).json()
    once = create(api, {**SAFE, "salary_max": 5000, "pay_period": "one_time"}).json()
    rows = rows_by_signal(compare(api, yearly["assessment_id"], once["assessment_id"]))
    assert rows["salary_monthly"] == {"signal": "salary_monthly", "a": 50000, "b": None, "better": "tie"}


def test_salary_min_is_used_when_only_the_minimum_is_given(api, ml):
    only_min = create(api, {**SAFE, "salary_min": 15000, "pay_period": "month"}).json()
    other = create(api, SAFE).json()
    assert rows_by_signal(compare(api, only_min["assessment_id"], other["assessment_id"]))["salary_monthly"]["a"] == 15000


def test_email_type_distinguishes_company_free_and_none(api, ml):
    none = create(api, {k: v for k, v in SAFE.items() if k != "contact_email"}).json()
    free = create(api, {**SAFE, "contact_email": "someone@yahoo.com"}).json()
    company = create(api, SAFE).json()
    r1 = rows_by_signal(compare(api, none["assessment_id"], free["assessment_id"]))["email_type"]
    r2 = rows_by_signal(compare(api, company["assessment_id"], free["assessment_id"]))["email_type"]
    assert (r1["a"], r1["b"], r1["better"]) == ("none", "free", "tie")
    assert (r2["a"], r2["b"], r2["better"]) == ("company", "free", "a")


def test_approved_reports_are_counted_and_pending_ones_are_not(api, pair, db_factory):
    with db_factory() as db:
        for kind, status in (("advance_fee", "approved"), ("fake_company", "approved"), ("other", "pending")):
            db.add(Report(assessment_id=pair[0]["assessment_id"], reporter_key=f"k-{kind}", report_type=kind,
                          description="x" * 12, status=status))
        db.commit()
    body = compare(api, pair[0]["assessment_id"], pair[1]["assessment_id"]).json()
    row = {r["signal"]: r for r in body["rows"]}["approved_reports"]
    assert (row["a"], row["b"], row["better"]) == (2, 0, "b")
    assert body["a"]["report_count_approved"] == 2


def test_connections_count_is_compared(api, ml):
    # first and second share the nexoralabs.example domain and e-mail; the third shares nothing
    first = create(api, SAFE).json()
    second = create(api, {**SAFE, "title": "Second posting"}).json()
    third = create(api, {**SAFE, "contact_email": "other@elsewhere.example", "title": "Third"}).json()
    both_linked = rows_by_signal(compare(api, first["assessment_id"], second["assessment_id"]))["connections_count"]
    assert (both_linked["a"], both_linked["b"], both_linked["better"]) == (2, 2, "tie")  # email + email_domain each
    mixed = rows_by_signal(compare(api, first["assessment_id"], third["assessment_id"]))["connections_count"]
    assert (mixed["a"], mixed["b"], mixed["better"]) == (2, 0, "b")


# ================================================================== privacy
def test_contact_details_are_never_part_of_the_comparison(api, pair):
    text = compare(api, pair[0]["assessment_id"], pair[1]["assessment_id"]).text
    for secret in ("brightpath.hr", "98765", "careers@nexoralabs", "gmail.com"):
        assert secret not in text


def test_compare_is_public_and_works_for_anonymous_assessments(api, pair):
    # no Authorization header and no owner token were sent
    assert compare(api, pair[0]["assessment_id"], pair[1]["assessment_id"]).status_code == 200


# ================================================================== errors
def test_equal_ids_are_400_bad_request(api, pair):
    err = assert_error(compare(api, pair[0]["assessment_id"], pair[0]["assessment_id"]), 400, "bad_request")
    assert "different" in err["message"]


def test_equal_ids_are_400_even_when_they_do_not_exist(api, ml):
    assert_error(compare(api, 424242, 424242), 400, "bad_request")


def test_a_missing_assessment_is_404_on_either_side(api, pair):
    real = pair[0]["assessment_id"]
    assert_error(compare(api, real, 999999), 404, "not_found")
    assert_error(compare(api, 999999, real), 404, "not_found")


@pytest.mark.parametrize("bad_id", [0, -5, 2**63, 10**30])
def test_out_of_range_ids_are_404(api, pair, bad_id):
    assert_error(compare(api, pair[0]["assessment_id"], bad_id), 404, "not_found")


def test_missing_fields_are_422_and_name_the_field(api, ml):
    err = assert_error(api.post(URL, json={"assessment_id_a": 1}), 422, "validation_error")
    assert err["fields"][0]["field"] == "assessment_id_b"


@pytest.mark.parametrize("bad", ["abc", None, 1.5, [], {}])
def test_ids_must_be_integers(api, ml, bad):
    assert_error(api.post(URL, json={"assessment_id_a": bad, "assessment_id_b": 1}), 422, "validation_error")


def test_malformed_json_is_400(api, ml):
    r = api.post(URL, content="{nope", headers={"Content-Type": "application/json"})
    assert_error(r, 400, "bad_request")


# ================================================================== wiring and regression
def test_compare_does_not_shadow_the_id_route(api, pair):
    # "compare" must not be read as an assessment id, and GET /{id} keeps working
    assert api.get(f"{BASE}/{pair[0]['assessment_id']}").status_code == 200
    assert api.get(f"{BASE}/compare").status_code == 422  # GET with a non-numeric id
    assert "post" in api.get("/openapi.json").json()["paths"]["/api/v1/assessments/compare"]
