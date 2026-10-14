"""Shared test setup.

Tests never need a real MySQL server:
  * DATABASE_URL points at a fake local URL. The engine is created lazily, so
    nothing connects unless a test asks for it.
  * Phase 1 tests replace the database calls used by the app (init_db, check_db).
  * Phase 2 tests that need a database use an in-memory SQLite database
    (guidebook B8) through the `db_factory` and `api` fixtures below.
The environment is set BEFORE app code is imported, so the cached settings are
the test settings and backend/.env on a developer laptop is ignored for these keys.
"""

from __future__ import annotations

import os

os.environ["ENV"] = "dev"
os.environ["DATABASE_URL"] = "mysql+pymysql://test_user:test_pw@localhost:3306/proofhire_test?charset=utf8mb4"
os.environ["CORS_ORIGINS"] = "http://localhost:5173"
# Phase 2: a fixed test-only secret (not a real one) and a fast bcrypt cost.
os.environ["JWT_SECRET"] = "test-only-jwt-secret-0123456789-abcdefghijklmnop"
os.environ["JWT_EXPIRE_MINUTES"] = "1440"
os.environ["BCRYPT_ROUNDS"] = "4"
# Blank values stop a developer's backend/.env from enabling admin seeding or the
# internal key during tests (real environment variables win over .env).
os.environ["ADMIN_EMAIL"] = ""
os.environ["ADMIN_PASSWORD"] = ""
os.environ["INTERNAL_API_KEY"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_JWT_SECRET = os.environ["JWT_SECRET"]


@pytest.fixture()
def client(monkeypatch):
    """TestClient with startup running but the database creation step stubbed out."""
    from app import main

    monkeypatch.setattr(main, "init_db", lambda: ())
    with TestClient(main.app) as c:
        yield c


# --------------------------------------------------------------------------
# Phase 2: in-memory SQLite database
# --------------------------------------------------------------------------
@pytest.fixture()
def db_factory():
    """A session factory bound to a fresh in-memory SQLite database with all 8 tables."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.db import models  # noqa: F401  (registers the tables)
    from app.db.base import Base

    # StaticPool + check_same_thread=False: every connection (including the
    # worker threads FastAPI uses for `def` routes) sees the same in-memory database.
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield factory
    engine.dispose()


def make_db_override(factory):
    """Same behaviour as app.db.session.get_db, but on the test database."""

    def override():
        db = factory()
        try:
            yield db
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    return override


@pytest.fixture()
def api(db_factory, monkeypatch):
    """TestClient for the real app, using the SQLite test database."""
    from app import main
    from app.db.session import get_db

    monkeypatch.setattr(main, "init_db", lambda: ())
    monkeypatch.setattr(main, "seed_admin", lambda: "skipped_no_config")
    main.app.dependency_overrides[get_db] = make_db_override(db_factory)
    try:
        with TestClient(main.app) as c:
            yield c
    finally:
        main.app.dependency_overrides.clear()


@pytest.fixture()
def db_override(db_factory):
    """A get_db replacement bound to the SQLite test database (for throw-away test apps)."""
    return make_db_override(db_factory)


# --------------------------------------------------------------------------
# Phase 3: fake ML package (TEST ONLY, see tests/ml_fakes.py)
# --------------------------------------------------------------------------
@pytest.fixture()
def ml(monkeypatch):
    """Install the fake ML modules; returns the state object with a .calls list."""
    from tests.ml_fakes import install_fake_ml

    return install_fake_ml(monkeypatch)
