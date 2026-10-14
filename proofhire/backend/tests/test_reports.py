"""Phase 5: POST /reports, GET /reports/mine, GET /admin/reports, PATCH /admin/reports/{id}
(guidebook Section 5.4 and B4).

Same setup as the earlier phases: the real app and routes, an in-memory SQLite database
and the TEST-ONLY fake ML package (only used to create assessments to report on).
"""

from __future__ import annotations

import pytest
from sqlalchemy import select, update

from app.core.security import create_access_token
from app.db.models import Report, User
from tests.test_assessments_api import BASE, RISKY, SAFE, assert_error, bearer, count, create, signup

REPORTS = "/api/v1/reports"
MINE = "/api/v1/reports/mine"
ADMIN = "/api/v1/admin/reports"

GOOD_TEXT = "They asked me to pay a registration fee on WhatsApp."
REPORT_TYPES = ["advance_fee", "impersonation", "personal_data_request", "fake_company", "harassment", "other"]
OUT_KEYS = {"id", "assessment_id", "report_type", "description", "status", "moderator_note", "created_at"}
ADMIN_ITEM_KEYS = {
    "id", "assessment_id", "listing_title", "company_name", "report_type", "description", "status", "created_at",
}


# ------------------------------------------------------------------ helpers
def report(api, assessment_id, *, token=None, report_type="advance_fee", description=GOOD_TEXT, headers=None, **extra):
    h = dict(bearer(token)) if token else {}
    h.update(headers or {})
    body = {"assessment_id": assessment_id, "report_type": report_type, "description": description, **extra}
    return api.post(REPORTS, json=body, headers=h)


def make_admin(api, db_factory, email="admin@example.com") -> str:
    """Register a normal user, then promote it in the database (registration can never make an admin)."""
    token, uid = signup(api, email)
    with db_factory() as db:
        db.execute(update(User).where(User.id == uid).values(role="admin"))
        db.commit()
    return token


def moderate(api, report_id, body, token=None):
    return api.patch(f"{ADMIN}/{report_id}", json=body, headers=bearer(token) if token else {})


def row(db_factory, report_id) -> Report:
    with db_factory() as db:
        return db.get(Report, report_id)


@pytest.fixture()
def aid(api, ml) -> int:
    """The id of one (anonymous) assessment to report on."""
    return create(api, RISKY).json()["assessment_id"]


@pytest.fixture()
def admin(api, db_factory) -> str:
    return make_admin(api, db_factory)


# ============================================================ POST /reports
def test_anonymous_report_returns_201_with_id_and_pending(api, aid, db_factory):
    r = report(api, aid)
    assert r.status_code == 201, r.text
    body = r.json()
    assert set(body) == {"id", "status"} and body["status"] == "pending"
    saved = row(db_factory, body["id"])
    assert saved.assessment_id == aid and saved.report_type == "advance_fee" and saved.description == GOOD_TEXT
    assert saved.status == "pending" and saved.reporter_user_id is None
    assert saved.moderator_id is None and saved.moderator_note is None and saved.reviewed_at is None
    assert len(saved.reporter_key) == 64 and all(c in "0123456789abcdef" for c in saved.reporter_key)  # sha256 hex


def test_logged_in_report_is_linked_to_the_user(api, aid, db_factory):
    token, uid = signup(api)
    r = report(api, aid, token=token)
    assert r.status_code == 201, r.text
    saved = row(db_factory, r.json()["id"])
    assert saved.reporter_user_id == uid and saved.reporter_key == str(uid)


@pytest.mark.parametrize("report_type", REPORT_TYPES)
def test_every_section_5_1_report_type_is_accepted(api, aid, report_type):
    assert report(api, aid, report_type=report_type).status_code == 201


def test_description_is_trimmed_before_it_is_saved(api, aid, db_factory):
    r = report(api, aid, description="   Asked for my Aadhaar number.   ")
    assert r.status_code == 201
    assert row(db_factory, r.json()["id"]).description == "Asked for my Aadhaar number."


def test_a_client_cannot_choose_the_status_or_reporter(api, aid, db_factory):
    """Extra body fields are ignored: a reporter cannot approve their own report."""
    r = report(api, aid, status="approved", moderator_id=1, reporter_key="x", reporter_user_id=1)
    assert r.status_code == 201 and r.json()["status"] == "pending"
    saved = row(db_factory, r.json()["id"])
    assert saved.status == "pending" and saved.moderator_id is None and saved.reporter_user_id is None
    assert saved.reporter_key != "x"


def test_a_pending_report_does_not_change_report_count_approved(api, aid):
    report(api, aid)
    assert api.get(f"{BASE}/{aid}").json()["report_count_approved"] == 0


# ------------------------------------------------------------ validation
def test_invalid_report_type_is_422_with_a_field(api, aid, db_factory):
    err = assert_error(report(api, aid, report_type="scam"), 422, "validation_error")
    assert [f["field"] for f in err["fields"]] == ["report_type"]
    assert count(db_factory, Report) == 0


@pytest.mark.parametrize("bad", ["", "         ", "123456789", "  123456789  ", "x" * 1001])
def test_description_outside_10_to_1000_characters_is_422(api, aid, db_factory, bad):
    err = assert_error(report(api, aid, description=bad), 422, "validation_error")
    assert [f["field"] for f in err["fields"]] == ["description"]
    assert count(db_factory, Report) == 0


@pytest.mark.parametrize("length", [10, 1000])
def test_description_boundaries_10_and_1000_are_accepted(api, aid, length):
    assert report(api, aid, description="x" * length).status_code == 201


def test_missing_fields_are_422(api, aid):
    for body in ({}, {"assessment_id": aid, "report_type": "other"}, {"assessment_id": aid, "description": GOOD_TEXT},
                 {"report_type": "other", "description": GOOD_TEXT}):
        assert_error(api.post(REPORTS, json=body), 422, "validation_error")


@pytest.mark.parametrize("bad_id", ["abc", "7", 7.5, True, None])
def test_assessment_id_must_be_an_integer(api, ml, bad_id):
    assert_error(report(api, bad_id), 422, "validation_error")


def test_description_must_be_a_string(api, aid):
    assert_error(report(api, aid, description=12345678901234), 422, "validation_error")


def test_body_that_is_not_json_is_400(api):
    r = api.post(REPORTS, content=b"{not json", headers={"Content-Type": "application/json"})
    assert_error(r, 400, "bad_request")


def test_unknown_assessment_is_404_and_nothing_is_saved(api, ml, db_factory):
    assert_error(report(api, 999999), 404, "not_found")
    assert_error(report(api, 2**63), 404, "not_found")  # beyond BIGINT: simply not found
    assert_error(report(api, 0), 404, "not_found")
    assert_error(report(api, -1), 404, "not_found")
    assert count(db_factory, Report) == 0


# --------------------------------------------------------------- duplicates
def test_same_user_same_assessment_same_type_is_409(api, aid, db_factory):
    token, _ = signup(api)
    assert report(api, aid, token=token).status_code == 201
    assert_error(report(api, aid, token=token), 409, "conflict")
    assert count(db_factory, Report) == 1


def test_duplicate_is_decided_by_assessment_reporter_and_type(api, aid, ml):
    token, _ = signup(api)
    other, _ = signup(api, "bob@example.com")
    second_aid = create(api, SAFE).json()["assessment_id"]
    assert report(api, aid, token=token).status_code == 201
    assert report(api, aid, token=token, report_type="fake_company").status_code == 201  # other type
    assert report(api, second_aid, token=token).status_code == 201  # other assessment
    assert report(api, aid, token=other).status_code == 201  # other reporter


def test_two_simultaneous_identical_reports_the_loser_gets_409(api, aid, db_factory, monkeypatch):
    """Both requests pass the duplicate check; the UNIQUE constraint uq_report_once stops the second."""
    from app.services import report_service

    assert report(api, aid).status_code == 201
    real = report_service._duplicate_exists
    calls = {"n": 0}

    def blind_first_time(*args, **kwargs):
        calls["n"] += 1
        return False if calls["n"] == 1 else real(*args, **kwargs)

    monkeypatch.setattr(report_service, "_duplicate_exists", blind_first_time)
    assert_error(report(api, aid), 409, "conflict")
    assert count(db_factory, Report) == 1


def test_anonymous_duplicate_from_the_same_ip_and_user_agent_is_409(api, aid):
    assert report(api, aid).status_code == 201
    assert_error(report(api, aid), 409, "conflict")


def test_anonymous_reporters_with_different_user_agent_or_ip_are_different_reporters(api, aid):
    assert report(api, aid, headers={"User-Agent": "agent-one"}).status_code == 201
    assert report(api, aid, headers={"User-Agent": "agent-two"}).status_code == 201
    assert_error(report(api, aid, headers={"User-Agent": "agent-one"}), 409, "conflict")
    # X-Forwarded-For: the FIRST value is the client (Render appends its own proxies after it).
    assert report(api, aid, headers={"User-Agent": "agent-one", "X-Forwarded-For": "203.0.113.5, 10.0.0.1"}).status_code == 201
    assert_error(
        report(api, aid, headers={"User-Agent": "agent-one", "X-Forwarded-For": "203.0.113.5, 10.9.9.9"}), 409, "conflict"
    )


# ------------------------------------------------------------------- auth
def test_invalid_or_expired_token_is_401_not_silently_anonymous(api, aid, db_factory):
    assert_error(report(api, aid, token="garbage"), 401, "unauthorized")
    _, uid = signup(api)
    expired = create_access_token(uid, "user", expires_minutes=-5)
    err = assert_error(report(api, aid, token=expired), 401, "unauthorized")
    assert err["message"] == "Token has expired"
    assert count(db_factory, Report) == 0


def test_token_of_a_deleted_user_is_401(api, aid, db_factory):
    token, uid = signup(api)
    with db_factory() as db:
        db.delete(db.get(User, uid))
        db.commit()
    assert_error(report(api, aid, token=token), 401, "unauthorized")


# ======================================================== GET /reports/mine
def test_mine_requires_login(api):
    assert_error(api.get(MINE), 401, "unauthorized")
    assert_error(api.get(MINE, headers=bearer("garbage")), 401, "unauthorized")


def test_mine_is_an_empty_list_for_a_user_with_no_reports(api):
    token, _ = signup(api)
    r = api.get(MINE, headers=bearer(token))
    assert r.status_code == 200 and r.json() == []


def test_mine_lists_only_my_reports_newest_first_with_exact_fields(api, aid, ml):
    token, _ = signup(api)
    other, _ = signup(api, "bob@example.com")
    second_aid = create(api, SAFE).json()["assessment_id"]
    first = report(api, aid, token=token, report_type="advance_fee").json()["id"]
    second = report(api, second_aid, token=token, report_type="other", description="Looks like a copied listing.").json()["id"]
    report(api, aid, token=other)  # someone else's
    report(api, aid)  # anonymous: not linked to any account

    r = api.get(MINE, headers=bearer(token))
    assert r.status_code == 200, r.text
    items = r.json()
    assert [i["id"] for i in items] == [second, first]
    for i in items:
        assert set(i) == OUT_KEYS and i["status"] == "pending" and i["moderator_note"] is None
        assert i["created_at"].endswith("Z") and "T" in i["created_at"]
    assert items[0]["assessment_id"] == second_aid and items[0]["report_type"] == "other"
    assert items[0]["description"] == "Looks like a copied listing."


# ======================================================== GET /admin/reports
def test_admin_list_requires_a_token(api):
    assert_error(api.get(ADMIN), 401, "unauthorized")
    assert_error(api.get(ADMIN, headers=bearer("garbage")), 401, "unauthorized")


def test_regular_user_cannot_list_admin_reports(api, aid):
    token, _ = signup(api)
    report(api, aid, token=token)
    assert_error(api.get(ADMIN, headers=bearer(token)), 403, "forbidden")


def test_token_that_only_claims_admin_is_still_403(api):
    _, uid = signup(api)
    forged_claim = create_access_token(uid, "admin")  # validly signed, but the database says "user"
    assert_error(api.get(ADMIN, headers=bearer(forged_claim)), 403, "forbidden")


def test_admin_sees_pending_reports_by_default_with_listing_title_and_company(api, aid, admin):
    rid = report(api, aid).json()["id"]
    r = api.get(ADMIN, headers=bearer(admin))
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"items", "total"} and body["total"] == 1
    item = body["items"][0]
    assert set(item) == ADMIN_ITEM_KEYS
    assert item["id"] == rid and item["assessment_id"] == aid and item["status"] == "pending"
    assert item["listing_title"] == RISKY["title"] and item["company_name"] == RISKY["company_name"]
    assert item["report_type"] == "advance_fee" and item["description"] == GOOD_TEXT


def test_admin_list_filters_by_status(api, aid, admin):
    keep_pending = report(api, aid, report_type="other").json()["id"]
    to_approve = report(api, aid, report_type="advance_fee").json()["id"]
    to_reject = report(api, aid, report_type="harassment").json()["id"]
    assert moderate(api, to_approve, {"status": "approved"}, admin).status_code == 200
    assert moderate(api, to_reject, {"status": "rejected"}, admin).status_code == 200

    def ids(status=None):
        url = ADMIN if status is None else f"{ADMIN}?status={status}"
        body = api.get(url, headers=bearer(admin)).json()
        assert body["total"] == len(body["items"])
        return [i["id"] for i in body["items"]]

    assert ids() == [keep_pending] and ids("pending") == [keep_pending]
    assert ids("approved") == [to_approve] and ids("rejected") == [to_reject]


def test_admin_list_paging_newest_first(api, aid, admin):
    made = [report(api, aid, report_type=t).json()["id"] for t in REPORT_TYPES]  # 6 reports
    page1 = api.get(f"{ADMIN}?page=1&limit=4", headers=bearer(admin)).json()
    page2 = api.get(f"{ADMIN}?page=2&limit=4", headers=bearer(admin)).json()
    assert page1["total"] == page2["total"] == 6
    assert [i["id"] for i in page1["items"]] == list(reversed(made))[:4]
    assert [i["id"] for i in page2["items"]] == list(reversed(made))[4:]
    assert api.get(f"{ADMIN}?page=9&limit=4", headers=bearer(admin)).json() == {"items": [], "total": 6}


@pytest.mark.parametrize("query", ["status=done", "status=", "page=0", "limit=0", "limit=51", "page=x"])
def test_admin_list_rejects_bad_query_values(api, admin, query):
    assert_error(api.get(f"{ADMIN}?{query}", headers=bearer(admin)), 422, "validation_error")


# ================================================== PATCH /admin/reports/{id}
def test_patch_requires_a_token(api, aid):
    rid = report(api, aid).json()["id"]
    assert_error(moderate(api, rid, {"status": "approved"}), 401, "unauthorized")
    assert_error(moderate(api, rid, {"status": "approved"}, "garbage"), 401, "unauthorized")


def test_regular_user_cannot_moderate_even_their_own_report(api, aid, db_factory):
    token, _ = signup(api)
    rid = report(api, aid, token=token).json()["id"]
    assert_error(moderate(api, rid, {"status": "approved"}, token), 403, "forbidden")
    assert row(db_factory, rid).status == "pending"


def test_admin_approves_with_a_note_and_gets_the_report_back(api, aid, admin, db_factory):
    rid = report(api, aid).json()["id"]
    r = moderate(api, rid, {"status": "approved", "moderator_note": "  Specific payment details given.  "}, admin)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == OUT_KEYS
    assert body["id"] == rid and body["assessment_id"] == aid and body["report_type"] == "advance_fee"
    assert body["description"] == GOOD_TEXT
    assert body["status"] == "approved" and body["moderator_note"] == "Specific payment details given."
    saved = row(db_factory, rid)
    assert saved.status == "approved" and saved.reviewed_at is not None
    with db_factory() as db:
        admin_id = db.scalar(select(User.id).where(User.email == "admin@example.com"))
    assert saved.moderator_id == admin_id


def test_admin_rejects_without_a_note(api, aid, admin, db_factory):
    rid = report(api, aid).json()["id"]
    r = moderate(api, rid, {"status": "rejected"}, admin)
    assert r.status_code == 200 and r.json()["status"] == "rejected" and r.json()["moderator_note"] is None
    assert row(db_factory, rid).reviewed_at is not None


def test_blank_note_is_stored_as_null(api, aid, admin):
    rid = report(api, aid).json()["id"]
    assert moderate(api, rid, {"status": "approved", "moderator_note": "   "}, admin).json()["moderator_note"] is None


def test_note_of_exactly_500_characters_is_accepted(api, aid, admin):
    rid = report(api, aid).json()["id"]
    r = moderate(api, rid, {"status": "approved", "moderator_note": "n" * 500}, admin)
    assert r.status_code == 200 and len(r.json()["moderator_note"]) == 500


@pytest.mark.parametrize(
    "body",
    [
        {"status": "pending"},  # a moderator decides, never resets
        {"status": "bogus"},
        {"status": "APPROVED"},
        {"status": None},
        {},
        {"moderator_note": "no status"},
        {"status": "approved", "moderator_note": "n" * 501},
        {"status": "approved", "moderator_note": 123},
    ],
)
def test_invalid_moderation_bodies_are_422_and_change_nothing(api, aid, admin, db_factory, body):
    rid = report(api, aid).json()["id"]
    assert_error(moderate(api, rid, body, admin), 422, "validation_error")
    assert row(db_factory, rid).status == "pending"


def test_nonexistent_report_is_404(api, admin):
    assert_error(moderate(api, 424242, {"status": "approved"}, admin), 404, "not_found")
    assert_error(moderate(api, 2**63, {"status": "approved"}, admin), 404, "not_found")
    assert_error(moderate(api, 0, {"status": "approved"}, admin), 404, "not_found")


def test_non_numeric_report_id_is_422(api, admin):
    assert_error(api.patch(f"{ADMIN}/abc", json={"status": "approved"}, headers=bearer(admin)), 422, "validation_error")


def test_unauthorised_caller_gets_401_or_403_before_404(api, db_factory):
    """Nothing about which report ids exist is revealed to non-admins."""
    token, _ = signup(api)
    assert_error(moderate(api, 424242, {"status": "approved"}), 401, "unauthorized")
    assert_error(moderate(api, 424242, {"status": "approved"}, token), 403, "forbidden")


def test_reviewing_twice_is_409_and_the_first_decision_stands(api, aid, admin, db_factory):
    rid = report(api, aid).json()["id"]
    assert moderate(api, rid, {"status": "approved", "moderator_note": "first"}, admin).status_code == 200
    first = row(db_factory, rid)
    assert_error(moderate(api, rid, {"status": "rejected", "moderator_note": "second"}, admin), 409, "conflict")
    assert_error(moderate(api, rid, {"status": "approved"}, admin), 409, "conflict")
    again = row(db_factory, rid)
    assert again.status == "approved" and again.moderator_note == "first" and again.reviewed_at == first.reviewed_at


def test_approved_report_raises_report_count_approved_and_rejected_does_not(api, aid, admin):
    approve_me = report(api, aid, report_type="advance_fee").json()["id"]
    reject_me = report(api, aid, report_type="harassment").json()["id"]
    moderate(api, reject_me, {"status": "rejected"}, admin)
    assert api.get(f"{BASE}/{aid}").json()["report_count_approved"] == 0
    moderate(api, approve_me, {"status": "approved"}, admin)
    assert api.get(f"{BASE}/{aid}").json()["report_count_approved"] == 1


def test_the_reporter_sees_the_decision_and_note_in_mine(api, aid, admin):
    token, _ = signup(api, "bob@example.com")
    rid = report(api, aid, token=token).json()["id"]
    moderate(api, rid, {"status": "rejected", "moderator_note": "Needs checkable details."}, admin)
    item = api.get(MINE, headers=bearer(token)).json()[0]
    assert item["id"] == rid and item["status"] == "rejected" and item["moderator_note"] == "Needs checkable details."


def test_an_admin_can_also_report_and_moderate_through_the_same_api(api, aid, admin):
    rid = report(api, aid, token=admin).json()["id"]
    assert moderate(api, rid, {"status": "approved"}, admin).status_code == 200


# ----------------------------------------------------- relationships (Section 6)
def test_deleting_the_assessment_deletes_its_reports(api, aid, db_factory):
    token, _ = signup(api)
    report(api, aid, token=token)  # on an anonymous assessment that stays
    owner = create(api, SAFE, token).json()  # a logged-in user's own assessment
    report(api, owner["assessment_id"], token=token)
    assert count(db_factory, Report) == 2
    assert api.delete(f"{BASE}/{owner['assessment_id']}", headers=bearer(token)).status_code == 204
    assert count(db_factory, Report) == 1


def test_phase_4_routes_still_registered(api):
    # Read the OpenAPI document, not app.routes: newer FastAPI keeps included routers as lazy
    # objects in app.routes that have no `.path`.
    r = api.get("/openapi.json")
    assert r.status_code == 200, r.text
    paths = set(r.json()["paths"])
    for p in (
        "/api/v1/assessments/compare",
        "/api/v1/assessments/{assessment_id}/checklist/{item_id}",
        "/api/v1/reports",
        "/api/v1/reports/mine",
        "/api/v1/admin/reports",
        "/api/v1/admin/reports/{report_id}",
    ):
        assert p in paths
