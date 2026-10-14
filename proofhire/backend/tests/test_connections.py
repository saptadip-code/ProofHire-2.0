"""Entity-connection detection and masking (guidebook B6, Section 6 idx_signal).

Rules under test:
  * signals match by BOTH signal_type and signal_value
  * the assessment being viewed never counts as its own match
  * times_seen = other assessments + 1; high_risk_count = how many OTHERS are high risk
  * emails and phones are masked; domains and company names stay visible
  * seeded demo rows are ignored unless include_demo is true

The fake ML package decides which entities each listing "contains", keyed by title,
so every test controls exactly which signals exist (tests/ml_fakes.py is TEST-ONLY).
"""

from __future__ import annotations

import json

from sqlalchemy import select, text

from app.db.models import Assessment, EntitySignal, Listing
from app.services.connection_service import (
    compute_connections,
    mask_email,
    mask_phone,
    mask_signal_value,
)
from tests.ml_fakes import install_fake_ml, stub_result
from tests.test_assessments_api import BASE, RISKY, SAFE, create


def install_entities(monkeypatch, by_title: dict[str, list[tuple[str, str]]]):
    """Fake ML whose entity list is looked up by listing title (RISKY scores high, SAFE low)."""

    def result(listing):
        r = stub_result(listing)
        r["entities"] = [{"type": t, "value": v} for t, v in by_title.get(listing["title"], [])]
        return r

    install_fake_ml(monkeypatch, result_fn=result)


def risky(title):
    return {**RISKY, "title": title}


def safe(title):
    return {**SAFE, "title": title}


def connections_of(api, assessment_id):
    return api.get(f"{BASE}/{assessment_id}").json()["connections"]


# ================================================================== matching rules
def test_a_single_assessment_never_matches_itself(api, monkeypatch):
    install_entities(monkeypatch, {"Only": [("email", "a@x.example"), ("email_domain", "x.example"), ("phone", "9876543210")]})
    created = create(api, risky("Only")).json()
    assert created["connections"] == []
    assert connections_of(api, created["assessment_id"]) == []


def test_times_seen_counts_the_others_plus_itself(api, monkeypatch):
    shared = [("website_domain", "shared.example")]
    install_entities(monkeypatch, {"One": shared, "Two": shared, "Three": shared})
    ids = [create(api, safe(t)).json()["assessment_id"] for t in ("One", "Two", "Three")]
    for assessment_id in ids:
        (conn,) = connections_of(api, assessment_id)
        assert conn["times_seen"] == 3 and conn["signal_type"] == "website_domain"


def test_high_risk_count_counts_only_the_others_and_never_the_viewer(api, monkeypatch):
    shared = [("website_domain", "shared.example")]
    install_entities(monkeypatch, {"High1": shared, "Low": shared, "High2": shared})
    high1 = create(api, risky("High1")).json()["assessment_id"]
    low = create(api, safe("Low")).json()["assessment_id"]
    high2 = create(api, risky("High2")).json()["assessment_id"]
    # High1 is itself high risk but must not count itself: the others are Low (no) and High2 (yes)
    assert connections_of(api, high1)[0]["high_risk_count"] == 1
    # Low sees two high-risk others
    assert connections_of(api, low)[0]["high_risk_count"] == 2
    assert connections_of(api, high2)[0]["high_risk_count"] == 1


def test_signals_match_by_type_and_value_not_by_value_alone(api, monkeypatch):
    install_entities(
        monkeypatch,
        {"Alpha listing": [("email_domain", "same.example")], "Bravo listing": [("website_domain", "same.example")]},
    )
    a = create(api, safe("Alpha listing")).json()["assessment_id"]
    create(api, safe("Bravo listing"))
    assert connections_of(api, a) == []


def test_unrelated_values_do_not_match(api, monkeypatch):
    install_entities(monkeypatch, {"Alpha listing": [("phone", "9876543210")], "Bravo listing": [("phone", "9876543211")]})
    a = create(api, safe("Alpha listing")).json()["assessment_id"]
    create(api, safe("Bravo listing"))
    assert connections_of(api, a) == []


def test_each_shared_signal_is_reported_once_with_its_own_counts(api, monkeypatch):
    install_entities(
        monkeypatch,
        {
            "Alpha listing": [("email_domain", "x.example"), ("phone", "9876543210")],
            "Bravo listing": [("email_domain", "x.example")],
            "Charlie listing": [("phone", "9876543210")],
        },
    )
    a = create(api, safe("Alpha listing")).json()["assessment_id"]
    create(api, safe("Bravo listing"))
    create(api, risky("Charlie listing"))
    by_type = {c["signal_type"]: c for c in connections_of(api, a)}
    assert set(by_type) == {"email_domain", "phone"}
    assert by_type["email_domain"]["times_seen"] == 2 and by_type["email_domain"]["high_risk_count"] == 0
    assert by_type["phone"]["times_seen"] == 2 and by_type["phone"]["high_risk_count"] == 1


def test_a_deleted_assessment_stops_counting(api, monkeypatch):
    shared = [("website_domain", "shared.example")]
    install_entities(monkeypatch, {"Alpha listing": shared, "Bravo listing": shared})
    a = create(api, safe("Alpha listing")).json()
    b = create(api, safe("Bravo listing")).json()
    assert len(connections_of(api, a["assessment_id"])) == 1
    deleted = api.delete(f"{BASE}/{b['assessment_id']}", headers={"X-Owner-Token": b["owner_token"]})
    assert deleted.status_code == 204
    assert connections_of(api, a["assessment_id"]) == []


def test_demo_rows_are_ignored_unless_include_demo_is_true(api, monkeypatch, db_factory):
    shared = [("website_domain", "shared.example")]
    install_entities(monkeypatch, {"Alpha listing": shared, "Bravo listing": shared})
    a = create(api, safe("Alpha listing")).json()["assessment_id"]
    b = create(api, safe("Bravo listing")).json()["assessment_id"]
    with db_factory() as db:
        listing = db.scalar(select(Listing).join(Assessment, Assessment.listing_id == Listing.id).where(Assessment.id == b))
        listing.is_synthetic_demo = True
        db.commit()
        signals = [("website_domain", "shared.example")]
        assert compute_connections(db, a, signals) == []
        with_demo = compute_connections(db, a, signals, include_demo=True)
        assert [(c["times_seen"], c["high_risk_count"]) for c in with_demo] == [(2, 0)]


# ================================================================== masking in the API
def test_phone_connections_are_masked_to_the_last_four_digits(api, monkeypatch):
    shared = [("phone", "9876543210")]
    install_entities(monkeypatch, {"Alpha listing": shared, "Bravo listing": shared})
    create(api, safe("Alpha listing"))
    b = create(api, safe("Bravo listing")).json()
    (conn,) = b["connections"]
    assert conn == {"signal_type": "phone", "value_masked": "******3210", "times_seen": 2, "high_risk_count": 0}
    assert "9876543210" not in json.dumps(b["connections"])


def test_email_connections_are_masked(api, monkeypatch):
    shared = [("email", "hr.careers@gmail.com")]
    install_entities(monkeypatch, {"Alpha listing": shared, "Bravo listing": shared})
    create(api, safe("Alpha listing"))
    (conn,) = create(api, safe("Bravo listing")).json()["connections"]
    assert conn["value_masked"] == "h***@gmail.com"
    assert "hr.careers" not in json.dumps(conn)


def test_domains_and_company_names_are_not_masked(api, monkeypatch):
    shared = [("email_domain", "nexoralabs.example"), ("website_domain", "nexoralabs.example"), ("company_name", "nexora")]
    install_entities(monkeypatch, {"Alpha listing": shared, "Bravo listing": shared})
    create(api, safe("Alpha listing"))
    conns = {c["signal_type"]: c["value_masked"] for c in create(api, safe("Bravo listing")).json()["connections"]}
    assert conns == {
        "email_domain": "nexoralabs.example",
        "website_domain": "nexoralabs.example",
        "company_name": "nexora",
    }


def test_connection_items_contain_only_the_contract_fields(api, monkeypatch):
    shared = [("website_domain", "shared.example")]
    install_entities(monkeypatch, {"Alpha listing": shared, "Bravo listing": shared})
    create(api, safe("Alpha listing"))
    (conn,) = create(api, safe("Bravo listing")).json()["connections"]
    assert set(conn) == {"signal_type", "value_masked", "times_seen", "high_risk_count"}


def test_viewers_who_are_not_the_owner_also_get_masked_entities(api, monkeypatch):
    install_entities(monkeypatch, {"Alpha listing": [("email", "hr.careers@gmail.com"), ("phone", "9876543210")]})
    created = create(api, safe("Alpha listing")).json()
    assert {"type": "email", "value": "hr.careers@gmail.com"} in created["entities"]  # owner sees real values
    stranger_view = api.get(f"{BASE}/{created['assessment_id']}").json()["entities"]
    assert {"type": "email", "value": "h***@gmail.com"} in stranger_view
    assert {"type": "phone", "value": "******3210"} in stranger_view


# ================================================================== masking helpers (unit)
def test_mask_email():
    assert mask_email("hr.careers@gmail.com") == "h***@gmail.com"
    assert mask_email("a@b.co") == "a***@b.co"
    assert mask_email("no-at-sign") == "***"
    assert mask_email("@nolocal.com") == "***"


def test_mask_phone():
    assert mask_phone("9876543210") == "******3210"
    assert mask_phone("+91 98765-43210") == "********3210"  # digits only (12 digits)
    assert mask_phone("1234") == "****"
    assert mask_phone("12") == "**"


def test_mask_signal_value_masks_only_email_and_phone():
    assert mask_signal_value("email", "a@b.co") == "a***@b.co"
    assert mask_signal_value("phone", "9876543210") == "******3210"
    for kind in ("email_domain", "website_domain", "company_name"):
        assert mask_signal_value(kind, "nexora.example") == "nexora.example"


# ================================================================== index
def test_signal_lookups_can_use_the_idx_signal_composite_index(db_factory):
    """The (signal_type, signal_value) equality lookup is answered from idx_signal.

    SQLite's plan is checked here; MySQL 8.4 uses the same index for the same predicate.
    """
    with db_factory() as db:
        plan = db.execute(
            text(
                "EXPLAIN QUERY PLAN SELECT assessment_id FROM entity_signals "
                "WHERE signal_type = 'email' AND signal_value = 'x@y.example'"
            )
        ).all()
    assert any("idx_signal" in str(row) for row in plan), plan
    assert {i.name for i in EntitySignal.__table__.indexes} >= {"idx_signal"}
