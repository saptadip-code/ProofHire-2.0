"""Admin bootstrap from ADMIN_EMAIL / ADMIN_PASSWORD (guidebook B2, B3 step 2)."""

from __future__ import annotations

import logging

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from app.core import security
from app.core.config import Settings
from app.db import seed
from app.db.models import User

GOOD_URL = "mysql+pymysql://proofhire:SECRETPW@localhost:3306/proofhire?charset=utf8mb4"
ADMIN_EMAIL = "Admin@ProofHire.dev"
ADMIN_PASSWORD = "a-strong-admin-pw-1"


def all_users(db_factory) -> list[User]:
    with db_factory() as db:
        return list(db.scalars(select(User).order_by(User.id)))


def settings_with(**extra) -> Settings:
    return Settings.model_validate({"database_url": GOOD_URL, **extra})


# ------------------------------------------------------ ensure_admin_user
def test_creates_admin_when_none_exists(db_factory):
    with db_factory() as db:
        assert seed.ensure_admin_user(db, ADMIN_EMAIL, ADMIN_PASSWORD) == seed.CREATED
    (admin,) = all_users(db_factory)
    assert admin.email == "admin@proofhire.dev"  # lower-cased
    assert admin.role == "admin"
    assert admin.is_active is True
    assert admin.display_name == seed.ADMIN_DISPLAY_NAME


def test_admin_password_is_stored_as_a_bcrypt_hash(db_factory):
    with db_factory() as db:
        seed.ensure_admin_user(db, ADMIN_EMAIL, ADMIN_PASSWORD)
    (admin,) = all_users(db_factory)
    assert admin.password_hash.startswith("$2")
    assert ADMIN_PASSWORD not in admin.password_hash
    assert security.verify_password(ADMIN_PASSWORD, admin.password_hash)


def test_is_idempotent_second_run_creates_nothing(db_factory):
    with db_factory() as db:
        assert seed.ensure_admin_user(db, ADMIN_EMAIL, ADMIN_PASSWORD) == seed.CREATED
    with db_factory() as db:
        assert seed.ensure_admin_user(db, ADMIN_EMAIL, ADMIN_PASSWORD) == seed.ADMIN_EXISTS
    assert len(all_users(db_factory)) == 1


def test_does_nothing_if_another_admin_already_exists(db_factory):
    with db_factory() as db:
        db.add(User(email="first@example.com", password_hash="x", display_name="First", role="admin", is_active=True))
        db.commit()
        assert seed.ensure_admin_user(db, ADMIN_EMAIL, ADMIN_PASSWORD) == seed.ADMIN_EXISTS
    assert [u.email for u in all_users(db_factory)] == ["first@example.com"]


def test_never_promotes_an_existing_regular_user(db_factory, caplog):
    with db_factory() as db:
        db.add(User(email="admin@proofhire.dev", password_hash="x", display_name="Squatter", role="user", is_active=True))
        db.commit()
    with caplog.at_level(logging.WARNING, logger="proofhire.seed"):
        with db_factory() as db:
            assert seed.ensure_admin_user(db, ADMIN_EMAIL, ADMIN_PASSWORD) == seed.EMAIL_TAKEN
    (user,) = all_users(db_factory)
    assert user.role == "user"  # unchanged
    assert user.password_hash == "x"  # password unchanged
    assert "NOT promoted" in caplog.text


@pytest.mark.parametrize("password", ["", "short", "1234567", "x" * 73, "é" * 37])
def test_rejects_unusable_admin_password(db_factory, password):
    with db_factory() as db:
        assert seed.ensure_admin_user(db, ADMIN_EMAIL, password) == seed.INVALID_CONFIG
    assert all_users(db_factory) == []


@pytest.mark.parametrize("email", ["", "not-an-email", "a@b"])
def test_rejects_invalid_admin_email(db_factory, email):
    with db_factory() as db:
        assert seed.ensure_admin_user(db, email, ADMIN_PASSWORD) == seed.INVALID_CONFIG
    assert all_users(db_factory) == []


def test_password_never_appears_in_logs(db_factory, caplog):
    with caplog.at_level(logging.DEBUG, logger="proofhire.seed"):
        with db_factory() as db:
            seed.ensure_admin_user(db, ADMIN_EMAIL, ADMIN_PASSWORD)
        with db_factory() as db:
            seed.ensure_admin_user(db, ADMIN_EMAIL, "short")
    assert ADMIN_PASSWORD not in caplog.text
    assert "short" not in caplog.text


# --------------------------------------------------------------- seed_admin
def test_seed_admin_without_configuration_touches_no_database(monkeypatch):
    monkeypatch.setattr(seed, "get_settings", lambda: settings_with())  # no ADMIN_* values

    def boom():
        raise AssertionError("the database must not be used when ADMIN_* is not set")

    monkeypatch.setattr(seed, "get_sessionmaker", boom)
    assert seed.seed_admin() == seed.SKIPPED


def test_seed_admin_needs_both_email_and_password(monkeypatch):
    monkeypatch.setattr(seed, "get_sessionmaker", lambda: (_ for _ in ()).throw(AssertionError("no DB")))
    monkeypatch.setattr(seed, "get_settings", lambda: settings_with(admin_email="a@example.com"))
    assert seed.seed_admin() == seed.SKIPPED
    monkeypatch.setattr(seed, "get_settings", lambda: settings_with(admin_password=ADMIN_PASSWORD))
    assert seed.seed_admin() == seed.SKIPPED


def test_seed_admin_creates_admin_from_settings(db_factory, monkeypatch):
    monkeypatch.setattr(
        seed, "get_settings", lambda: settings_with(admin_email=ADMIN_EMAIL, admin_password=ADMIN_PASSWORD)
    )
    monkeypatch.setattr(seed, "get_sessionmaker", lambda: db_factory)
    assert seed.seed_admin() == seed.CREATED
    with db_factory() as db:
        assert db.scalar(select(func.count()).select_from(User).where(User.role == "admin")) == 1


def test_seed_admin_never_raises_when_the_database_is_down(monkeypatch):
    monkeypatch.setattr(
        seed, "get_settings", lambda: settings_with(admin_email=ADMIN_EMAIL, admin_password=ADMIN_PASSWORD)
    )

    def down():
        raise OperationalError("SELECT 1", {}, Exception(2003, "Can't connect to MySQL server"))

    monkeypatch.setattr(seed, "get_sessionmaker", down)
    assert seed.seed_admin() == seed.FAILED


# ------------------------------------------------------- end to end (API)
def test_seeded_admin_can_log_in_and_is_an_admin(api, db_factory):
    with db_factory() as db:
        seed.ensure_admin_user(db, ADMIN_EMAIL, ADMIN_PASSWORD)
    r = api.post("/api/v1/auth/login", json={"email": "admin@proofhire.dev", "password": ADMIN_PASSWORD})
    assert r.status_code == 200
    assert r.json()["user"]["role"] == "admin"
    token = r.json()["access_token"]
    me = api.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["role"] == "admin"


def test_public_registration_can_never_create_an_admin(api):
    r = api.post(
        "/api/v1/auth/register",
        json={"email": "evil@example.com", "password": "password-123", "display_name": "Evil", "role": "admin"},
    )
    assert r.status_code == 201
    assert r.json()["user"]["role"] == "user"
