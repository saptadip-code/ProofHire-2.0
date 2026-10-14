"""Auth dependencies and role-based access control, on a small throw-away app.

(This file deliberately does not use `from __future__ import annotations`: the
routes are defined inside a fixture, and FastAPI must be able to read their
annotations directly.)
"""

from typing import Optional

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core import deps, security
from app.core.config import Settings
from app.core.deps import get_current_user, get_optional_user, require_admin, verify_internal_key
from app.core.errors import register_exception_handlers
from app.db.models import User
from app.db.session import get_db

GOOD_URL = "mysql+pymysql://proofhire:SECRETPW@localhost:3306/proofhire?charset=utf8mb4"


@pytest.fixture()
def mini(db_override):
    app = FastAPI()
    register_exception_handlers(app)
    app.dependency_overrides[get_db] = db_override

    @app.get("/user-only")
    def user_only(user: User = Depends(get_current_user)):
        return {"id": user.id, "role": user.role}

    @app.get("/admin-only")
    def admin_only(user: User = Depends(require_admin)):
        return {"id": user.id, "role": user.role}

    @app.get("/optional")
    def optional(user: Optional[User] = Depends(get_optional_user)):
        return {"id": user.id if user else None}

    @app.post("/internal")
    def internal(_: None = Depends(verify_internal_key)):
        return {"ok": True}

    with TestClient(app) as c:
        yield c


def make_user(db_factory, email: str, role: str = "user", active: bool = True) -> int:
    with db_factory() as db:
        user = User(
            email=email,
            password_hash=security.hash_password("a-test-password"),
            display_name="Test User",
            role=role,
            is_active=active,
        )
        db.add(user)
        db.commit()
        return user.id


def auth(user_id: int, role: str = "user", **kw) -> dict:
    return {"Authorization": f"Bearer {security.create_access_token(user_id, role, **kw)}"}


def code_of(response) -> str:
    return response.json()["error"]["code"]


# ------------------------------------------------------- get_current_user
def test_protected_route_without_token_is_401(mini):
    r = mini.get("/user-only")
    assert r.status_code == 401 and code_of(r) == "unauthorized"


def test_protected_route_with_valid_token(mini, db_factory):
    uid = make_user(db_factory, "u@example.com")
    r = mini.get("/user-only", headers=auth(uid))
    assert r.status_code == 200
    assert r.json() == {"id": uid, "role": "user"}


def test_protected_route_with_expired_token_is_401(mini, db_factory):
    uid = make_user(db_factory, "u@example.com")
    r = mini.get("/user-only", headers=auth(uid, expires_minutes=-1))
    assert r.status_code == 401 and "expired" in r.json()["error"]["message"].lower()


def test_protected_route_with_invalid_token_is_401(mini):
    r = mini.get("/user-only", headers={"Authorization": "Bearer nonsense"})
    assert r.status_code == 401 and code_of(r) == "unauthorized"


def test_disabled_user_loses_access_even_with_a_valid_token(mini, db_factory):
    uid = make_user(db_factory, "off@example.com", active=False)
    assert mini.get("/user-only", headers=auth(uid)).status_code == 401


# ---------------------------------------------------------- require_admin
def test_admin_can_use_admin_route(mini, db_factory):
    uid = make_user(db_factory, "admin@example.com", role="admin")
    r = mini.get("/admin-only", headers=auth(uid, "admin"))
    assert r.status_code == 200 and r.json()["role"] == "admin"


def test_regular_user_is_forbidden_on_admin_route(mini, db_factory):
    uid = make_user(db_factory, "u@example.com")
    r = mini.get("/admin-only", headers=auth(uid, "user"))
    assert r.status_code == 403 and code_of(r) == "forbidden"
    assert set(r.json()["error"]) == {"code", "message", "fields"}


def test_admin_route_without_token_is_401_not_403(mini):
    r = mini.get("/admin-only")
    assert r.status_code == 401 and code_of(r) == "unauthorized"


def test_token_claiming_admin_does_not_make_a_user_admin(mini, db_factory):
    """The role in the token is ignored: the database decides."""
    uid = make_user(db_factory, "sneaky@example.com", role="user")
    r = mini.get("/admin-only", headers=auth(uid, "admin"))  # validly signed, lies about role
    assert r.status_code == 403


def test_admin_role_comes_from_the_database_not_the_token(mini, db_factory):
    uid = make_user(db_factory, "real-admin@example.com", role="admin")
    r = mini.get("/admin-only", headers=auth(uid, "user"))  # old token still says "user"
    assert r.status_code == 200


def test_demoted_admin_loses_access_immediately(mini, db_factory):
    uid = make_user(db_factory, "was-admin@example.com", role="admin")
    headers = auth(uid, "admin")
    assert mini.get("/admin-only", headers=headers).status_code == 200
    with db_factory() as db:
        db.scalar(select(User).where(User.id == uid)).role = "user"
        db.commit()
    assert mini.get("/admin-only", headers=headers).status_code == 403


def test_disabled_admin_is_401(mini, db_factory):
    uid = make_user(db_factory, "off-admin@example.com", role="admin", active=False)
    assert mini.get("/admin-only", headers=auth(uid, "admin")).status_code == 401


# ------------------------------------------------------ get_optional_user
def test_optional_user_anonymous_when_no_header(mini):
    r = mini.get("/optional")
    assert r.status_code == 200 and r.json() == {"id": None}


def test_optional_user_returns_the_user_with_a_valid_token(mini, db_factory):
    uid = make_user(db_factory, "u@example.com")
    assert mini.get("/optional", headers=auth(uid)).json() == {"id": uid}


def test_optional_user_with_a_bad_token_is_401_not_anonymous(mini):
    r = mini.get("/optional", headers={"Authorization": "Bearer nonsense"})
    assert r.status_code == 401


def test_optional_user_with_an_expired_token_is_401(mini, db_factory):
    uid = make_user(db_factory, "u@example.com")
    assert mini.get("/optional", headers=auth(uid, expires_minutes=-1)).status_code == 401


# ---------------------------------------------------- verify_internal_key
def _with_internal_key(monkeypatch, key):
    s = Settings.model_validate({"database_url": GOOD_URL, "internal_api_key": key} if key else {"database_url": GOOD_URL})
    monkeypatch.setattr(deps, "get_settings", lambda: s)


def test_internal_key_check_is_skipped_when_not_configured(mini, monkeypatch):
    _with_internal_key(monkeypatch, None)
    assert mini.post("/internal").status_code == 200


def test_internal_key_required_when_configured(mini, monkeypatch):
    _with_internal_key(monkeypatch, "s3cret-internal-key")
    missing = mini.post("/internal")
    wrong = mini.post("/internal", headers={"X-Internal-Key": "nope"})
    right = mini.post("/internal", headers={"X-Internal-Key": "s3cret-internal-key"})
    assert missing.status_code == 401 and code_of(missing) == "unauthorized"
    assert wrong.status_code == 401
    assert right.status_code == 200
