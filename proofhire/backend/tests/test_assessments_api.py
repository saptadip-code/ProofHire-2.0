"""POST/GET/DELETE /api/v1/assessments (guidebook Section 5.3-5.5, B4).

The ML package is replaced by TEST-ONLY fakes (tests/ml_fakes.py). Everything
else is the real code: gateway, service, router, models, and an in-memory SQLite database.
"""

from __future__ import annotations

import hashlib
import re

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import (
    Assessment,
    AssessmentChecklistItem,
    EntitySignal,
    EvidenceItem,
    Listing,
    LlmCall,
    Report,
)
from app.services import assessment_service
from tests.ml_fakes import Wrapped, install_fake_ml, remove_ml, stub_result

BASE = "/api/v1/assessments"
REGISTER = "/api/v1/auth/register"

RISKY = {
    "title": "Data Entry Intern - Earn 40000 per month!!",
    "company_name": "Brightpath Careers",
    "description": "Work from home. No experience needed. Pay registration fee of Rs 1499 to confirm your seat.",
    "salary_min": 40000,
    "salary_max": 40000,
    "pay_period": "month",
    "contact_email": "brightpath.hr@gmail.com",
    "contact_phone": "+91 98765 43210",
    "application_channel": "whatsapp",
    "upfront_fee_amount": 1499,
    "interview_mode": "chat_only",
}
SAFE = {
    "title": "Backend Engineering Intern",
    "company_name": "Nexora Labs",
    "description": "Join our platform team for six months, with a mentor and weekly code reviews.",
    "requirements": "Python basics, SQL, and curiosity about how web services work.",
    "location": "Bengaluru",
    "contact_email": "careers@nexoralabs.example",
    "company_website": "https://nexoralabs.example",
    "application_channel": "email",
    "interview_mode": "video_call",
}

TOP_KEYS = {
    "assessment_id", "created_at", "listing", "risk_score", "risk_level", "thresholds", "model_version",
    "evidence", "explanation", "checklist", "entities", "connections", "report_count_approved", "disclaimer",
}
LISTING_KEYS = {
    "title", "company_name", "description", "requirements", "location", "work_mode", "employment_type",
    "salary_min", "salary_max", "pay_period", "currency", "contact_email", "contact_phone",
    "application_channel", "company_website", "upfront_fee_amount", "interview_mode",
}


# ------------------------------------------------------------------ helpers
def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def signup(api, email: str = "alice@example.com") -> tuple[str, int]:
    r = api.post(REGISTER, json={"email": email, "password": "correct-horse-1", "display_name": "Test User"})
    assert r.status_code == 201, r.text
    body = r.json()
    return body["access_token"], body["user"]["id"]


def create(api, payload: dict = RISKY, token: str | None = None):
    return api.post(BASE, json=payload, headers=bearer(token) if token else {})


def count(db_factory, model) -> int:
    with db_factory() as db:
        return db.scalar(select(func.count()).select_from(model))


def assert_error(response, status: int, code: str) -> dict:
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "fields"}
    assert body["error"]["code"] == code
    return body["error"]


# ================================================================== POST: success
def test_anonymous_create_returns_201_with_the_assessment_result_contract(api, ml):
    r = create(api)
    assert r.status_code == 201, r.text
    body = r.json()
    assert set(body) == TOP_KEYS | {"owner_token"}
    assert isinstance(body["assessment_id"], int)
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", body["created_at"])
    assert set(body["listing"]) == LISTING_KEYS
    assert body["risk_score"] == 0.91 and body["risk_level"] == "high"
    assert body["thresholds"] == {"low": 0.35, "high": 0.7}
    assert body["model_version"] == "proofhire-lr-stub-test"
    assert [e["id"] for e in body["evidence"]] == ["E1", "E2"]
    assert set(body["evidence"][0]) == {"id", "code", "label", "type", "direction", "severity", "snippet", "weight"}
    assert body["evidence"][0]["weight"] is None and body["evidence"][1]["weight"] == 1.84
    assert set(body["explanation"]) == {"source", "summary", "key_concerns", "what_to_verify"}
    assert body["explanation"]["source"] == "template"
    assert body["explanation"]["key_concerns"] == [{"text": "An upfront fee is requested.", "evidence_ids": ["E1"]}]
    assert [c["code"] for c in body["checklist"]] == ["CHK_NO_FEE", "CHK_GENERAL_RECRUITER"]
    assert set(body["checklist"][0]) == {"id", "code", "text", "priority", "done"}
    assert all(c["done"] is False and isinstance(c["id"], int) for c in body["checklist"])
    assert {"type": "email", "value": "brightpath.hr@gmail.com"} in body["entities"]
    assert body["connections"] == []
    assert body["report_count_approved"] == 0
    assert body["disclaimer"] == "ProofHire gives a risk estimate, not a verification of the employer."


def test_authenticated_create_has_no_owner_token_key(api, ml, db_factory):
    token, user_id = signup(api)
    r = create(api, RISKY, token)
    assert r.status_code == 201, r.text
    assert set(r.json()) == TOP_KEYS  # no owner_token at all
    with db_factory() as db:
        a = db.scalar(select(Assessment))
        assert a.user_id == user_id
        assert a.owner_token_hash is None


def test_low_risk_listing_uses_the_ml_result_unchanged(api, ml):
    r = create(api, SAFE)
    assert r.status_code == 201
    assert r.json()["risk_score"] == 0.12 and r.json()["risk_level"] == "low"


def test_pipeline_receives_the_validated_listing_with_defaults(api, ml):
    create(api, {**SAFE, "title": "  Backend Engineering Intern  "})
    assert len(ml.calls) == 1
    sent = ml.calls[0]
    assert sent["title"] == "Backend Engineering Intern"
    assert sent["currency"] == "INR" and sent["work_mode"] == "onsite" and sent["upfront_fee_amount"] == 0


def test_pydantic_object_result_from_the_pipeline_is_accepted(api, monkeypatch):
    install_fake_ml(monkeypatch, result_fn=lambda l: Wrapped(**stub_result(l)))
    assert create(api).status_code == 201


# ================================================================== POST: persistence
def test_everything_is_persisted(api, ml, db_factory):
    r = create(api)
    aid = r.json()["assessment_id"]
    with db_factory() as db:
        listing = db.scalar(select(Listing))
        assert listing.is_synthetic_demo is False  # ordinary submissions are never demo rows
        assert listing.title == RISKY["title"] and listing.upfront_fee_amount == 1499
        assert listing.currency == "INR" and listing.work_mode == "onsite"

        a = db.get(Assessment, aid)
        assert a.listing_id == listing.id
        assert float(a.risk_score) == 0.91 and a.risk_level == "high"
        assert float(a.threshold_low) == 0.35 and float(a.threshold_high) == 0.7
        assert a.model_version == "proofhire-lr-stub-test"
        assert a.explanation_source == "template"
        assert a.summary.startswith("Test summary")
        assert a.key_concerns == [{"text": "An upfront fee is requested.", "evidence_ids": ["E1"]}]
        assert a.what_to_verify == ["Ask for the company's registered legal name."]
        assert a.user_id is None

        ev = list(db.scalars(select(EvidenceItem).order_by(EvidenceItem.sort_order)))
        assert [(e.public_id, e.code, e.evidence_type, e.sort_order) for e in ev] == [
            ("E1", "UPFRONT_FEE", "observed", 0),
            ("E2", "MODEL_TERM", "model", 1),
        ]
        assert ev[0].weight is None and float(ev[1].weight) == 1.84 and ev[0].snippet == "registration fee of Rs 1,499"

        items = list(db.scalars(select(AssessmentChecklistItem)))
        assert {(c.code, c.priority, c.is_done) for c in items} == {("CHK_NO_FEE", 1, False), ("CHK_GENERAL_RECRUITER", 3, False)}

        signals = {(s.signal_type, s.signal_value) for s in db.scalars(select(EntitySignal))}
        assert signals == {("email", "brightpath.hr@gmail.com")}  # gmail.com domain is not stored as a signal

        calls = list(db.scalars(select(LlmCall)))
        assert len(calls) == 1 and calls[0].assessment_id == aid and calls[0].provider == "template"


def test_free_mail_domains_are_not_stored_as_domain_signals(api, monkeypatch, db_factory):
    def with_free_mail(listing):
        result = stub_result(listing)
        result["entities"] += [
            {"type": "email_domain", "value": "gmail.com"},
            {"type": "website_domain", "value": "Yahoo.com"},
            {"type": "website_domain", "value": "brightpath.example"},
            {"type": "phone", "value": "9876543210"},
            {"type": "phone", "value": "9876543210"},  # duplicate
        ]
        return result

    install_fake_ml(monkeypatch, result_fn=with_free_mail)
    assert create(api).status_code == 201
    with db_factory() as db:
        signals = {(s.signal_type, s.signal_value) for s in db.scalars(select(EntitySignal))}
    assert signals == {
        ("email", "brightpath.hr@gmail.com"),
        ("website_domain", "brightpath.example"),
        ("phone", "9876543210"),
    }


def test_duplicate_checklist_codes_do_not_break_saving(api, monkeypatch, db_factory):
    def dup(listing):
        result = stub_result(listing)
        result["checklist"].append({"code": "CHK_NO_FEE", "text": "Duplicate", "priority": 2})
        return result

    install_fake_ml(monkeypatch, result_fn=dup)
    r = create(api)
    assert r.status_code == 201
    assert len(r.json()["checklist"]) == 2
    assert count(db_factory, AssessmentChecklistItem) == 2


def test_result_without_llm_meta_stores_no_llm_call(api, monkeypatch, db_factory):
    def no_meta(listing):
        result = stub_result(listing)
        result.pop("llm_meta")
        return result

    install_fake_ml(monkeypatch, result_fn=no_meta)
    assert create(api).status_code == 201
    assert count(db_factory, LlmCall) == 0


# ================================================================== POST: anonymous owner token
def test_owner_token_is_random_and_only_its_sha256_is_stored(api, ml, db_factory):
    first, second = create(api).json(), create(api).json()
    t1, t2 = first["owner_token"], second["owner_token"]
    assert len(t1) == 32 and t1 != t2
    with db_factory() as db:
        stored = {a.id: a.owner_token_hash for a in db.scalars(select(Assessment))}
    assert stored[first["assessment_id"]] == hashlib.sha256(t1.encode()).hexdigest()
    assert t1 not in stored.values() and len(stored[first["assessment_id"]]) == 64


def test_raw_owner_token_is_never_returned_again(api, ml):
    created = create(api).json()
    token = created["owner_token"]
    fetched = api.get(f"{BASE}/{created['assessment_id']}", headers={"X-Owner-Token": token})
    assert fetched.status_code == 200
    assert "owner_token" not in fetched.json()
    assert token not in fetched.text and "owner_token_hash" not in fetched.text


# ================================================================== POST: validation and errors
def test_validation_error_uses_the_standard_shape_and_saves_nothing(api, ml, db_factory):
    r = create(api, {**RISKY, "salary_min": 50000, "salary_max": 40000})
    err = assert_error(r, 422, "validation_error")
    assert err["fields"][0]["field"] == "salary_max"
    assert "salary_min" in err["fields"][0]["message"]
    assert ml.calls == []
    assert count(db_factory, Listing) == 0 and count(db_factory, Assessment) == 0


def test_missing_required_fields_are_listed(api, ml):
    err = assert_error(create(api, {}), 422, "validation_error")
    assert {f["field"] for f in err["fields"]} == {"title", "company_name", "description"}


@pytest.mark.parametrize(
    "bad",
    [
        {"title": "ab"},
        {"description": "too short"},
        {"work_mode": "office"},
        {"contact_email": "not-an-email"},
        {"contact_phone": "call me"},
        {"company_website": "example.com"},
        {"upfront_fee_amount": -5},
        {"currency": "RUPEES"},
    ],
)
def test_invalid_listing_fields_are_rejected_with_422(api, ml, bad):
    assert_error(create(api, {**SAFE, **bad}), 422, "validation_error")
    assert ml.calls == []


def test_malformed_json_is_400_bad_request(api, ml):
    r = api.post(BASE, content=b"{not json", headers={"Content-Type": "application/json"})
    assert_error(r, 400, "bad_request")


def test_invalid_token_on_create_is_401_not_silently_anonymous(api, ml, db_factory):
    assert_error(create(api, SAFE, token="garbage"), 401, "unauthorized")
    assert count(db_factory, Assessment) == 0


# ================================================================== POST: ML failures
def test_missing_ml_package_returns_503_model_unavailable(api, monkeypatch, db_factory):
    remove_ml(monkeypatch)
    err = assert_error(create(api), 503, "model_unavailable")
    assert err["fields"] == []
    assert count(db_factory, Listing) == 0 and count(db_factory, Assessment) == 0


def test_model_not_loaded_returns_503_and_does_not_score(api, monkeypatch, db_factory):
    state = install_fake_ml(monkeypatch, loaded=False)
    assert_error(create(api), 503, "model_unavailable")
    assert state.calls == []
    assert count(db_factory, Assessment) == 0


def test_pipeline_crash_is_a_generic_500_without_leaking_details(api, monkeypatch, db_factory):
    install_fake_ml(monkeypatch, raises=ValueError("SECRET-LISTING-TEXT"))
    r = create(api)
    err = assert_error(r, 500, "internal_error")
    assert "SECRET" not in r.text and "ValueError" not in err["message"]
    assert count(db_factory, Assessment) == 0


def test_result_that_breaks_the_documented_shape_is_a_500_and_saves_nothing(api, monkeypatch, db_factory):
    install_fake_ml(monkeypatch, result_fn=lambda listing: {"risk_score": 7, "risk_level": "extreme"})
    assert_error(create(api), 500, "internal_error")
    assert count(db_factory, Listing) == 0


def test_database_failure_midway_leaves_no_partial_records(api, ml, db_factory, monkeypatch):
    def boom(db, assessment_id, result):
        db.add(
            EvidenceItem(
                assessment_id=assessment_id, public_id="E9", code="X", label="x",
                evidence_type="observed", direction="increases_risk", severity=1, sort_order=0,
            )
        )
        raise SQLAlchemyError("simulated failure after the listing and assessment were flushed")

    monkeypatch.setattr(assessment_service, "_add_children", boom)
    r = create(api)
    err = assert_error(r, 500, "internal_error")
    assert err["message"] == "Could not save the assessment"
    for model in (Listing, Assessment, EvidenceItem, AssessmentChecklistItem, EntitySignal, LlmCall):
        assert count(db_factory, model) == 0, model.__name__


# ================================================================== GET /assessments/{id}
def test_get_with_owner_token_returns_full_contact_details(api, ml):
    created = create(api).json()
    r = api.get(f"{BASE}/{created['assessment_id']}", headers={"X-Owner-Token": created["owner_token"]})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == TOP_KEYS
    assert body["listing"]["contact_email"] == RISKY["contact_email"]
    assert body["listing"]["contact_phone"] == RISKY["contact_phone"]
    assert {"type": "email", "value": RISKY["contact_email"]} in body["entities"]
    assert body["risk_score"] == 0.91 and body["evidence"][0]["id"] == "E1"


def test_get_by_id_without_credentials_masks_contact_details(api, ml):
    aid = create(api).json()["assessment_id"]
    r = api.get(f"{BASE}/{aid}")
    assert r.status_code == 200
    body = r.json()
    assert body["listing"]["contact_email"] == "b***@gmail.com"
    assert body["listing"]["contact_phone"].endswith("3210") and "98765" not in r.text
    assert {"type": "email", "value": "b***@gmail.com"} in body["entities"]
    assert "brightpath.hr" not in r.text
    assert body["listing"]["title"] == RISKY["title"]  # everything else is visible


def test_wrong_owner_token_sees_the_masked_view(api, ml):
    aid = create(api).json()["assessment_id"]
    r = api.get(f"{BASE}/{aid}", headers={"X-Owner-Token": "wrong-token"})
    assert r.status_code == 200
    assert r.json()["listing"]["contact_email"] == "b***@gmail.com"


def test_owner_user_sees_details_and_other_user_sees_masked(api, ml):
    owner_token, _ = signup(api, "owner@example.com")
    other_token, _ = signup(api, "other@example.com")
    aid = create(api, RISKY, owner_token).json()["assessment_id"]
    mine = api.get(f"{BASE}/{aid}", headers=bearer(owner_token)).json()
    theirs = api.get(f"{BASE}/{aid}", headers=bearer(other_token)).json()
    assert mine["listing"]["contact_email"] == RISKY["contact_email"]
    assert theirs["listing"]["contact_email"] == "b***@gmail.com"


def test_anonymous_owner_token_does_not_unlock_for_a_logged_in_stranger(api, ml):
    created = create(api).json()
    stranger, _ = signup(api, "stranger@example.com")
    r = api.get(f"{BASE}/{created['assessment_id']}", headers=bearer(stranger))
    assert r.json()["listing"]["contact_email"] == "b***@gmail.com"


def test_get_unknown_id_is_404(api, ml):
    assert_error(api.get(f"{BASE}/999"), 404, "not_found")


@pytest.mark.parametrize("bad_id", ["0", "-3", str(2**70)])
def test_get_out_of_range_ids_are_404(api, ml, bad_id):
    assert_error(api.get(f"{BASE}/{bad_id}"), 404, "not_found")


def test_get_non_numeric_id_is_422(api, ml):
    assert_error(api.get(f"{BASE}/abc"), 422, "validation_error")


def test_get_with_invalid_token_is_401(api, ml):
    aid = create(api).json()["assessment_id"]
    assert_error(api.get(f"{BASE}/{aid}", headers=bearer("garbage")), 401, "unauthorized")


# ================================================================== connections and report counts
def test_repeat_domain_creates_connections_on_both_assessments(api, ml):
    a = create(api, SAFE).json()  # low risk, careers@nexoralabs.example
    b = create(api, {**RISKY, "contact_email": "payments@nexoralabs.example", "contact_phone": None}).json()  # high risk
    conn_a = api.get(f"{BASE}/{a['assessment_id']}").json()["connections"]
    conn_b = api.get(f"{BASE}/{b['assessment_id']}").json()["connections"]
    assert conn_a == [{"signal_type": "email_domain", "value_masked": "nexoralabs.example", "times_seen": 2, "high_risk_count": 1}]
    assert conn_b == [{"signal_type": "email_domain", "value_masked": "nexoralabs.example", "times_seen": 2, "high_risk_count": 0}]
    assert b["connections"] == conn_b  # the creation response already contains them


def test_repeat_email_is_masked_in_connections(api, ml):
    create(api, SAFE)
    second = create(api, {**SAFE, "title": "Second posting"})
    conns = {c["signal_type"]: c for c in second.json()["connections"]}
    assert conns["email"] == {"signal_type": "email", "value_masked": "c***@nexoralabs.example", "times_seen": 2, "high_risk_count": 0}
    assert all("careers@" not in c["value_masked"] for c in conns.values())


def test_demo_rows_are_not_counted_as_connections(api, ml, db_factory):
    a = create(api, SAFE).json()
    b = create(api, {**SAFE, "title": "Second posting"}).json()
    with db_factory() as db:
        listing = db.scalar(select(Listing).join(Assessment, Assessment.listing_id == Listing.id).where(Assessment.id == b["assessment_id"]))
        listing.is_synthetic_demo = True
        db.commit()
    assert api.get(f"{BASE}/{a['assessment_id']}").json()["connections"] == []


def test_report_count_approved_counts_only_approved_reports(api, ml, db_factory):
    aid = create(api).json()["assessment_id"]
    with db_factory() as db:
        for kind, status in (("advance_fee", "approved"), ("fake_company", "approved"), ("other", "pending"), ("harassment", "rejected")):
            db.add(Report(assessment_id=aid, reporter_key=f"k-{kind}", report_type=kind, description="x" * 12, status=status))
        db.commit()
    assert api.get(f"{BASE}/{aid}").json()["report_count_approved"] == 2


# ================================================================== GET /assessments (list)
def test_list_requires_login(api, ml):
    assert_error(api.get(BASE), 401, "unauthorized")
    assert_error(api.get(BASE, headers=bearer("garbage")), 401, "unauthorized")


def test_list_returns_only_the_callers_assessments(api, ml):
    alice, _ = signup(api, "alice@example.com")
    bob, _ = signup(api, "bob@example.com")
    mine = create(api, SAFE, alice).json()["assessment_id"]
    create(api, RISKY, bob)
    create(api, RISKY)  # anonymous: belongs to nobody
    r = api.get(BASE, headers=bearer(alice))
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"items", "total", "page", "limit"}
    assert body["total"] == 1 and [i["id"] for i in body["items"]] == [mine]
    assert body["page"] == 1 and body["limit"] == 20


def test_list_item_shape(api, ml, db_factory):
    token, _ = signup(api)
    aid = create(api, RISKY, token).json()["assessment_id"]
    with db_factory() as db:
        db.add(Report(assessment_id=aid, reporter_key="k", report_type="advance_fee", description="x" * 12, status="approved"))
        db.commit()
    item = api.get(BASE, headers=bearer(token)).json()["items"][0]
    assert set(item) == {"id", "created_at", "title", "company_name", "risk_score", "risk_level", "evidence_count", "report_count_approved"}
    assert item["title"] == RISKY["title"] and item["company_name"] == RISKY["company_name"]
    assert item["risk_score"] == 0.91 and item["risk_level"] == "high"
    assert item["evidence_count"] == 2 and item["report_count_approved"] == 1
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", item["created_at"])


def test_list_is_newest_first_and_paginated(api, ml):
    token, _ = signup(api)
    ids = [create(api, {**SAFE, "title": f"Posting number {n}"}, token).json()["assessment_id"] for n in range(5)]
    page1 = api.get(BASE, params={"limit": 2}, headers=bearer(token)).json()
    page2 = api.get(BASE, params={"limit": 2, "page": 2}, headers=bearer(token)).json()
    page3 = api.get(BASE, params={"limit": 2, "page": 3}, headers=bearer(token)).json()
    assert page1["total"] == 5 and page1["limit"] == 2 and page1["page"] == 1
    assert [i["id"] for i in page1["items"]] == [ids[4], ids[3]]
    assert [i["id"] for i in page2["items"]] == [ids[2], ids[1]]
    assert [i["id"] for i in page3["items"]] == [ids[0]]
    assert api.get(BASE, params={"page": 9}, headers=bearer(token)).json()["items"] == []


def test_list_filters_by_risk_level(api, ml):
    token, _ = signup(api)
    create(api, SAFE, token)
    create(api, RISKY, token)
    create(api, {**RISKY, "title": "Another risky offer"}, token)
    high = api.get(BASE, params={"risk_level": "high"}, headers=bearer(token)).json()
    low = api.get(BASE, params={"risk_level": "low"}, headers=bearer(token)).json()
    medium = api.get(BASE, params={"risk_level": "medium"}, headers=bearer(token)).json()
    assert high["total"] == 2 and all(i["risk_level"] == "high" for i in high["items"])
    assert low["total"] == 1 and medium["total"] == 0 and medium["items"] == []


@pytest.mark.parametrize("params", [{"risk_level": "extreme"}, {"limit": 51}, {"limit": 0}, {"page": 0}])
def test_list_rejects_bad_query_parameters(api, ml, params):
    token, _ = signup(api)
    assert_error(api.get(BASE, params=params, headers=bearer(token)), 422, "validation_error")


def test_list_accepts_the_maximum_limit(api, ml):
    token, _ = signup(api)
    assert api.get(BASE, params={"limit": 50}, headers=bearer(token)).status_code == 200


# ================================================================== DELETE
def test_owner_deletes_and_every_related_row_is_removed(api, ml, db_factory):
    token, _ = signup(api)
    aid = create(api, RISKY, token).json()["assessment_id"]
    with db_factory() as db:
        db.add(Report(assessment_id=aid, reporter_key="k", report_type="other", description="x" * 12))
        db.commit()
    r = api.delete(f"{BASE}/{aid}", headers=bearer(token))
    assert r.status_code == 204 and r.content == b""
    assert_error(api.get(f"{BASE}/{aid}"), 404, "not_found")
    for model in (Listing, Assessment, EvidenceItem, AssessmentChecklistItem, EntitySignal, Report):
        assert count(db_factory, model) == 0, model.__name__
    with db_factory() as db:  # the LLM log survives with a NULL link (Section 6)
        calls = list(db.scalars(select(LlmCall)))
    assert len(calls) == 1 and calls[0].assessment_id is None


def test_anonymous_owner_can_delete_with_the_owner_token(api, ml, db_factory):
    created = create(api).json()
    r = api.delete(f"{BASE}/{created['assessment_id']}", headers={"X-Owner-Token": created["owner_token"]})
    assert r.status_code == 204
    assert count(db_factory, Assessment) == 0


def test_delete_by_another_user_is_403_and_changes_nothing(api, ml, db_factory):
    owner, _ = signup(api, "owner@example.com")
    other, _ = signup(api, "other@example.com")
    aid = create(api, RISKY, owner).json()["assessment_id"]
    assert_error(api.delete(f"{BASE}/{aid}", headers=bearer(other)), 403, "forbidden")
    assert count(db_factory, Assessment) == 1 and count(db_factory, Listing) == 1


def test_delete_without_credentials_is_403(api, ml, db_factory):
    aid = create(api).json()["assessment_id"]
    assert_error(api.delete(f"{BASE}/{aid}"), 403, "forbidden")
    assert count(db_factory, Assessment) == 1


def test_delete_with_wrong_owner_token_is_403(api, ml, db_factory):
    aid = create(api).json()["assessment_id"]
    assert_error(api.delete(f"{BASE}/{aid}", headers={"X-Owner-Token": "nope"}), 403, "forbidden")
    assert count(db_factory, Assessment) == 1


def test_delete_anonymous_assessment_by_logged_in_stranger_is_403(api, ml, db_factory):
    aid = create(api).json()["assessment_id"]
    stranger, _ = signup(api, "stranger@example.com")
    assert_error(api.delete(f"{BASE}/{aid}", headers=bearer(stranger)), 403, "forbidden")
    assert count(db_factory, Assessment) == 1


def test_delete_unknown_id_is_404(api, ml):
    token, _ = signup(api)
    assert_error(api.delete(f"{BASE}/12345", headers=bearer(token)), 404, "not_found")


def test_delete_with_invalid_token_is_401(api, ml):
    aid = create(api).json()["assessment_id"]
    assert_error(api.delete(f"{BASE}/{aid}", headers=bearer("garbage")), 401, "unauthorized")


def test_deleting_one_assessment_leaves_the_others(api, ml, db_factory):
    token, _ = signup(api)
    first = create(api, SAFE, token).json()["assessment_id"]
    second = create(api, RISKY, token).json()["assessment_id"]
    assert api.delete(f"{BASE}/{first}", headers=bearer(token)).status_code == 204
    assert api.get(f"{BASE}/{second}").status_code == 200
    assert count(db_factory, Assessment) == 1 and count(db_factory, Listing) == 1
    assert count(db_factory, EvidenceItem) == 2


# ================================================================== wiring
def test_assessment_routes_are_registered_and_swagger_loads(api):
    paths = api.get("/openapi.json").json()["paths"]
    assert set(paths["/api/v1/assessments"]) == {"get", "post"}
    assert set(paths["/api/v1/assessments/{assessment_id}"]) == {"get", "delete"}
    assert api.get("/docs").status_code == 200
