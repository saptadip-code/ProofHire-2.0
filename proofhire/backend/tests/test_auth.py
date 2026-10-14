"""POST /auth/register, POST /auth/login, GET /auth/me (guidebook B4, Section 5.4/5.5)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from sqlalchemy import select

from app.core import security
from app.db.models import User

SECRET = os.environ["JWT_SECRET"]  # set in conftest.py
REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"

GOOD = {"email": "alice@example.com", "password": "correct-horse-1", "display_name": "Alice"}


def register(api, **overrides):
    return api.post(REGISTER, json={**GOOD, **overrides})


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def assert_error(response, status: int, code: str):
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "fields"}
    assert body["error"]["code"] == code
    return body["error"]


def users_in_db(db_factory) -> list[User]:
    with db_factory() as db:
        return list(db.scalars(select(User).order_by(User.id)))


# ------------------------------------------------------------- register
def test_register_success_returns_token_and_user(api):
    r = register(api)
    assert r.status_code == 201
    body = r.json()
    assert set(body) == {"access_token", "token_type", "user"}
    assert body["token_type"] == "bearer"
    assert set(body["user"]) == {"id", "email", "display_name", "role"}
    assert body["user"]["email"] == "alice@example.com"
    assert body["user"]["display_name"] == "Alice"
    assert body["user"]["role"] == "user"
    assert isinstance(body["user"]["id"], int)


def test_register_token_works_immediately(api):
    body = register(api).json()
    me = api.get(ME, headers=bearer(body["access_token"]))
    assert me.status_code == 200
    assert me.json() == body["user"]


def test_register_stores_a_bcrypt_hash_never_the_password(api, db_factory):
    r = register(api)
    users = users_in_db(db_factory)
    assert len(users) == 1
    stored = users[0].password_hash
    assert stored.startswith("$2")
    assert GOOD["password"] not in stored
    assert security.verify_password(GOOD["password"], stored)
    # Nothing secret in the response either.
    assert "password" not in r.text.lower()  # no password or password_hash field in the response
    assert stored not in r.text


def test_register_normalises_email_and_name(api):
    r = register(api, email="  Alice@Example.COM ", display_name="  Alice  ")
    assert r.status_code == 201
    assert r.json()["user"]["email"] == "alice@example.com"
    assert r.json()["user"]["display_name"] == "Alice"


def test_register_duplicate_email_is_409(api, db_factory):
    assert register(api).status_code == 201
    err = assert_error(register(api, display_name="Someone else"), 409, "conflict")
    assert "already exists" in err["message"]
    assert len(users_in_db(db_factory)) == 1


def test_register_duplicate_email_is_case_insensitive(api):
    assert register(api).status_code == 201
    assert_error(register(api, email="ALICE@example.com"), 409, "conflict")


def test_register_cannot_choose_a_role(api):
    r = api.post(REGISTER, json={**GOOD, "role": "admin", "is_active": False, "id": 99})
    assert r.status_code == 201
    assert r.json()["user"]["role"] == "user"
    assert r.json()["user"]["id"] != 99


@pytest.mark.parametrize(
    "overrides,field",
    [
        ({"password": "short12"}, "password"),  # 7 characters
        ({"password": "x" * 73}, "password"),  # 73 characters
        ({"password": "é" * 37}, "password"),  # 37 characters but 74 bytes
        ({"email": "not-an-email"}, "email"),
        ({"email": "a@b"}, "email"),
        ({"email": "a b@example.com"}, "email"),
        ({"email": "a" * 250 + "@example.com"}, "email"),
        ({"display_name": ""}, "display_name"),
        ({"display_name": "   "}, "display_name"),
        ({"display_name": "n" * 101}, "display_name"),
    ],
)
def test_register_validation_errors_are_422_with_field(api, overrides, field):
    r = register(api, **overrides)
    err = assert_error(r, 422, "validation_error")
    assert field in {f["field"] for f in err["fields"]}
    assert all(set(f) == {"field", "message"} for f in err["fields"])


def test_register_password_limits_accept_8_and_72(api):
    assert register(api, email="eight@example.com", password="12345678").status_code == 201
    assert register(api, email="seventytwo@example.com", password="p" * 72).status_code == 201


def test_register_missing_fields_are_422(api):
    r = api.post(REGISTER, json={"email": "x@example.com"})
    err = assert_error(r, 422, "validation_error")
    assert {"password", "display_name"} <= {f["field"] for f in err["fields"]}


def test_register_validation_error_never_echoes_the_password(api):
    r = register(api, password="tiny-pw")
    assert r.status_code == 422
    assert "tiny-pw" not in r.text


def test_register_malformed_json_is_400(api):
    r = api.post(REGISTER, content="{not json", headers={"Content-Type": "application/json"})
    assert_error(r, 400, "bad_request")


# ---------------------------------------------------------------- login
def test_login_success(api):
    registered = register(api).json()
    r = api.post(LOGIN, json={"email": GOOD["email"], "password": GOOD["password"]})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"access_token", "token_type", "user"}
    assert body["token_type"] == "bearer"
    assert body["user"] == registered["user"]
    claims = jwt.decode(body["access_token"], SECRET, algorithms=["HS256"])
    assert claims["sub"] == str(registered["user"]["id"])
    assert claims["role"] == "user"


def test_login_email_is_case_insensitive(api):
    register(api)
    r = api.post(LOGIN, json={"email": "  ALICE@Example.com ", "password": GOOD["password"]})
    assert r.status_code == 200


def test_login_wrong_password_is_401(api):
    register(api)
    err = assert_error(api.post(LOGIN, json={"email": GOOD["email"], "password": "wrong-password"}), 401, "unauthorized")
    assert err["message"] == "Invalid email or password"


def test_login_unknown_email_gets_the_same_401_as_wrong_password(api):
    register(api)
    wrong_pw = api.post(LOGIN, json={"email": GOOD["email"], "password": "wrong-password"})
    unknown = api.post(LOGIN, json={"email": "nobody@example.com", "password": "wrong-password"})
    assert unknown.status_code == wrong_pw.status_code == 401
    assert unknown.json() == wrong_pw.json()


def test_login_sets_www_authenticate_on_401(api):
    r = api.post(LOGIN, json={"email": "nobody@example.com", "password": "whatever-1"})
    assert r.headers.get("www-authenticate") == "Bearer"


def test_login_overlong_password_is_a_plain_401(api):
    register(api)
    r = api.post(LOGIN, json={"email": GOOD["email"], "password": "x" * 500})
    assert_error(r, 401, "unauthorized")


def test_login_disabled_account_is_401(api, db_factory):
    register(api)
    with db_factory() as db:
        user = db.scalar(select(User).where(User.email == GOOD["email"]))
        user.is_active = False
        db.commit()
    r = api.post(LOGIN, json={"email": GOOD["email"], "password": GOOD["password"]})
    err = assert_error(r, 401, "unauthorized")
    assert err["message"] == "Invalid email or password"


def test_login_missing_fields_are_422(api):
    assert_error(api.post(LOGIN, json={"email": "a@example.com"}), 422, "validation_error")
    assert_error(api.post(LOGIN, json={"password": "something-1"}), 422, "validation_error")


# ------------------------------------------------------------------- me
def test_me_requires_a_token(api):
    err = assert_error(api.get(ME), 401, "unauthorized")
    assert "required" in err["message"].lower()


def test_me_returns_the_current_user(api):
    body = register(api).json()
    r = api.get(ME, headers=bearer(body["access_token"]))
    assert r.status_code == 200
    assert set(r.json()) == {"id", "email", "display_name", "role"}


@pytest.mark.parametrize("header", ["Bearer", "Bearer ", "Basic abc123", "Token abc123", "abc123"])
def test_me_rejects_missing_or_wrong_scheme(api, header):
    assert_error(api.get(ME, headers={"Authorization": header}), 401, "unauthorized")


def test_me_rejects_garbage_token(api):
    assert_error(api.get(ME, headers=bearer("not.a.jwt")), 401, "unauthorized")


def test_me_rejects_expired_token(api):
    uid = register(api).json()["user"]["id"]
    expired = security.create_access_token(uid, "user", expires_minutes=-1)
    err = assert_error(api.get(ME, headers=bearer(expired)), 401, "unauthorized")
    assert "expired" in err["message"].lower()


def test_me_rejects_token_signed_with_wrong_secret(api):
    uid = register(api).json()["user"]["id"]
    forged = jwt.encode(
        {"sub": str(uid), "role": "user", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        "another-secret-that-is-long-enough-0123456789",
        algorithm="HS256",
    )
    assert_error(api.get(ME, headers=bearer(forged)), 401, "unauthorized")


def test_me_rejects_alg_none_token(api):
    uid = register(api).json()["user"]["id"]
    unsigned = jwt.encode(
        {"sub": str(uid), "role": "admin", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        None,
        algorithm="none",
    )
    assert_error(api.get(ME, headers=bearer(unsigned)), 401, "unauthorized")


def test_me_rejects_token_for_a_user_that_does_not_exist(api):
    ghost = security.create_access_token(9999, "user")
    assert_error(api.get(ME, headers=bearer(ghost)), 401, "unauthorized")


def test_me_rejects_token_of_a_disabled_account(api, db_factory):
    body = register(api).json()
    with db_factory() as db:
        user = db.scalar(select(User).where(User.id == body["user"]["id"]))
        user.is_active = False
        db.commit()
    assert_error(api.get(ME, headers=bearer(body["access_token"])), 401, "unauthorized")


def test_me_sets_www_authenticate_on_401(api):
    assert api.get(ME).headers.get("www-authenticate") == "Bearer"


def test_auth_routes_are_documented_in_openapi(api):
    paths = api.get("/openapi.json").json()["paths"]
    assert "/api/v1/auth/register" in paths
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/auth/me" in paths
