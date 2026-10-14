"""PATCH /api/v1/assessments/{id}/checklist/{item_id} (guidebook Section 5.4, B4).

Same setup as test_assessments_api.py: real app code and routes, an in-memory
SQLite database and the TEST-ONLY fake ML package.
"""

from __future__ import annotations

import pytest

from app.db.models import AssessmentChecklistItem
from tests.test_assessments_api import BASE, RISKY, SAFE, assert_error, bearer, create, signup


def patch(api, assessment_id, item_id, body=None, *, token=None, owner_token=None):
    headers = {}
    if token:
        headers.update(bearer(token))
    if owner_token:
        headers["X-Owner-Token"] = owner_token
    return api.patch(
        f"{BASE}/{assessment_id}/checklist/{item_id}",
        json={"done": True} if body is None else body,
        headers=headers,
    )


def item_row(db_factory, item_id):
    with db_factory() as db:
        return db.get(AssessmentChecklistItem, item_id)


@pytest.fixture()
def owned(api, ml):
    """A logged-in user's assessment: (token, assessment dict)."""
    token, _ = signup(api)
    return token, create(api, RISKY, token).json()


@pytest.fixture()
def anonymous(api, ml):
    """An anonymous assessment (the creation response carries owner_token)."""
    return create(api, RISKY).json()


# ================================================================== success
def test_owner_ticks_an_item_and_gets_id_and_done_only(api, owned, db_factory):
    token, a = owned
    item = a["checklist"][0]
    r = patch(api, a["assessment_id"], item["id"], {"done": True}, token=token)
    assert r.status_code == 200, r.text
    assert r.json() == {"id": item["id"], "done": True}  # exactly {id, done}
    row = item_row(db_factory, item["id"])
    assert row.is_done is True and row.done_at is not None


def test_the_new_state_is_visible_in_the_assessment(api, owned):
    token, a = owned
    first, second = a["checklist"]
    patch(api, a["assessment_id"], first["id"], {"done": True}, token=token)
    got = api.get(f"{BASE}/{a['assessment_id']}", headers=bearer(token)).json()["checklist"]
    assert [(c["id"], c["done"]) for c in got] == [(first["id"], True), (second["id"], False)]


def test_unticking_clears_done_and_done_at(api, owned, db_factory):
    token, a = owned
    item_id = a["checklist"][0]["id"]
    patch(api, a["assessment_id"], item_id, {"done": True}, token=token)
    r = patch(api, a["assessment_id"], item_id, {"done": False}, token=token)
    assert r.status_code == 200 and r.json() == {"id": item_id, "done": False}
    row = item_row(db_factory, item_id)
    assert row.is_done is False and row.done_at is None


def test_repeating_the_same_value_is_allowed_and_keeps_the_first_tick_time(api, owned, db_factory):
    token, a = owned
    item_id = a["checklist"][0]["id"]
    assert patch(api, a["assessment_id"], item_id, {"done": True}, token=token).status_code == 200
    first = item_row(db_factory, item_id).done_at
    again = patch(api, a["assessment_id"], item_id, {"done": True}, token=token)
    assert again.status_code == 200 and again.json()["done"] is True
    assert item_row(db_factory, item_id).done_at == first
    # unticking something that is not ticked is also fine
    other = a["checklist"][1]["id"]
    assert patch(api, a["assessment_id"], other, {"done": False}, token=token).json() == {"id": other, "done": False}


def test_only_the_chosen_item_changes(api, owned, db_factory):
    token, a = owned
    first, second = a["checklist"]
    patch(api, a["assessment_id"], first["id"], {"done": True}, token=token)
    assert item_row(db_factory, second["id"]).is_done is False


# ================================================================== anonymous owner token
def test_anonymous_owner_can_update_with_the_owner_token(api, anonymous, db_factory):
    item_id = anonymous["checklist"][0]["id"]
    r = patch(api, anonymous["assessment_id"], item_id, {"done": True}, owner_token=anonymous["owner_token"])
    assert r.status_code == 200 and r.json() == {"id": item_id, "done": True}
    assert item_row(db_factory, item_id).is_done is True


def test_anonymous_assessment_without_a_token_is_403(api, anonymous, db_factory):
    item_id = anonymous["checklist"][0]["id"]
    r = patch(api, anonymous["assessment_id"], item_id, {"done": True})
    assert_error(r, 403, "forbidden")
    assert item_row(db_factory, item_id).is_done is False


def test_wrong_owner_token_is_403(api, anonymous, db_factory):
    item_id = anonymous["checklist"][0]["id"]
    r = patch(api, anonymous["assessment_id"], item_id, {"done": True}, owner_token="x" * 32)
    assert_error(r, 403, "forbidden")
    assert item_row(db_factory, item_id).is_done is False


def test_the_sha256_hash_is_not_accepted_as_a_token(api, anonymous):
    import hashlib

    stored_hash = hashlib.sha256(anonymous["owner_token"].encode()).hexdigest()
    r = patch(api, anonymous["assessment_id"], anonymous["checklist"][0]["id"], owner_token=stored_hash)
    assert_error(r, 403, "forbidden")


def test_a_token_from_another_assessment_does_not_work(api, ml):
    first, second = create(api, RISKY).json(), create(api, SAFE).json()
    r = patch(api, second["assessment_id"], second["checklist"][0]["id"], owner_token=first["owner_token"])
    assert_error(r, 403, "forbidden")


def test_a_logged_in_stranger_cannot_update_an_anonymous_assessment(api, anonymous):
    stranger, _ = signup(api, "stranger@example.com")
    r = patch(api, anonymous["assessment_id"], anonymous["checklist"][0]["id"], token=stranger)
    assert_error(r, 403, "forbidden")


def test_the_owner_token_never_comes_back_in_the_response(api, anonymous):
    r = patch(api, anonymous["assessment_id"], anonymous["checklist"][0]["id"], owner_token=anonymous["owner_token"])
    assert "owner_token" not in r.text and anonymous["owner_token"] not in r.text


# ================================================================== authenticated ownership
def test_another_user_is_403_and_nothing_changes(api, owned, db_factory):
    _, a = owned
    other, _ = signup(api, "bob@example.com")
    item_id = a["checklist"][0]["id"]
    r = patch(api, a["assessment_id"], item_id, {"done": True}, token=other)
    assert_error(r, 403, "forbidden")
    assert item_row(db_factory, item_id).is_done is False


def test_no_credentials_on_a_users_assessment_is_403(api, owned):
    _, a = owned
    assert_error(patch(api, a["assessment_id"], a["checklist"][0]["id"]), 403, "forbidden")


def test_invalid_token_is_401_not_silently_anonymous(api, owned):
    _, a = owned
    r = patch(api, a["assessment_id"], a["checklist"][0]["id"], token="not.a.jwt")
    assert_error(r, 401, "unauthorized")


def test_ownership_is_checked_before_the_item_so_strangers_learn_nothing(api, owned):
    _, a = owned
    stranger, _ = signup(api, "eve@example.com")
    assert_error(patch(api, a["assessment_id"], 999999, token=stranger), 403, "forbidden")


# ================================================================== 404s
def test_unknown_assessment_is_404(api, ml):
    assert_error(patch(api, 999999, 1), 404, "not_found")


def test_unknown_item_is_404(api, owned):
    token, a = owned
    assert_error(patch(api, a["assessment_id"], 999999, token=token), 404, "not_found")


def test_an_item_of_another_assessment_is_404(api, ml):
    token, _ = signup(api)
    first = create(api, RISKY, token).json()
    second = create(api, SAFE, token).json()
    foreign_item = second["checklist"][0]["id"]
    r = patch(api, first["assessment_id"], foreign_item, {"done": True}, token=token)
    assert_error(r, 404, "not_found")


@pytest.mark.parametrize("bad_id", [0, -1, 2**63, 10**30])
def test_out_of_range_ids_are_404(api, owned, bad_id):
    token, a = owned
    assert_error(patch(api, bad_id, 1, token=token), 404, "not_found")
    assert_error(patch(api, a["assessment_id"], bad_id, token=token), 404, "not_found")


def test_non_numeric_ids_are_422(api, ml):
    assert api.patch(f"{BASE}/abc/checklist/1", json={"done": True}).status_code == 422
    assert api.patch(f"{BASE}/1/checklist/abc", json={"done": True}).status_code == 422


# ================================================================== body validation
def test_missing_done_is_422(api, owned):
    token, a = owned
    err = assert_error(patch(api, a["assessment_id"], a["checklist"][0]["id"], {}, token=token), 422, "validation_error")
    assert err["fields"][0]["field"] == "done"


@pytest.mark.parametrize("bad", ["yes", "true", 1, 0, None, [], {}])
def test_done_must_be_a_real_boolean(api, owned, db_factory, bad):
    token, a = owned
    item_id = a["checklist"][0]["id"]
    r = patch(api, a["assessment_id"], item_id, {"done": bad}, token=token)
    assert_error(r, 422, "validation_error")
    assert item_row(db_factory, item_id).is_done is False


def test_malformed_json_is_400(api, owned):
    token, a = owned
    r = api.patch(
        f"{BASE}/{a['assessment_id']}/checklist/{a['checklist'][0]['id']}",
        content="{not json",
        headers={**bearer(token), "Content-Type": "application/json"},
    )
    assert_error(r, 400, "bad_request")


# ================================================================== wiring
def test_patch_route_is_documented_in_swagger(api):
    paths = api.get("/openapi.json").json()["paths"]
    assert "patch" in paths["/api/v1/assessments/{assessment_id}/checklist/{item_id}"]
