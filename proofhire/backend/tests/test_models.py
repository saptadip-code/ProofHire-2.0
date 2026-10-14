"""The eight Section 6 tables, checked against SQLAlchemy metadata (no database needed).

The expectations below are typed from guidebook Section 6, not copied from models.py,
so a drifting model fails here.
"""

from __future__ import annotations

import pytest
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

from app.db import models  # noqa: F401  (registers tables)
from app.db.base import Base
from app.db.init_db import EXPECTED_TABLES

COLUMNS = {
    "users": ["id", "email", "password_hash", "display_name", "role", "is_active", "created_at"],
    "listings": [
        "id", "title", "company_name", "description", "requirements", "location", "work_mode",
        "employment_type", "salary_min", "salary_max", "pay_period", "currency", "contact_email",
        "contact_phone", "application_channel", "company_website", "upfront_fee_amount",
        "interview_mode", "is_synthetic_demo", "created_at",
    ],
    "assessments": [
        "id", "user_id", "listing_id", "owner_token_hash", "risk_score", "risk_level", "threshold_low",
        "threshold_high", "model_version", "explanation_source", "summary", "key_concerns",
        "what_to_verify", "created_at",
    ],
    "evidence_items": [
        "id", "assessment_id", "public_id", "code", "label", "evidence_type", "direction", "severity",
        "snippet", "weight", "sort_order",
    ],
    "assessment_checklist_items": ["id", "assessment_id", "code", "text", "priority", "is_done", "done_at"],
    "entity_signals": ["id", "assessment_id", "signal_type", "signal_value", "created_at"],
    "reports": [
        "id", "assessment_id", "reporter_user_id", "reporter_key", "report_type", "description", "status",
        "moderator_id", "moderator_note", "created_at", "reviewed_at",
    ],
    "llm_calls": ["id", "assessment_id", "provider", "model", "latency_ms", "success", "error_code", "created_at"],
}

# (table, column) -> (referred table, ondelete)
FOREIGN_KEYS = {
    ("assessments", "user_id"): ("users", "SET NULL"),
    ("assessments", "listing_id"): ("listings", "CASCADE"),
    ("evidence_items", "assessment_id"): ("assessments", "CASCADE"),
    ("assessment_checklist_items", "assessment_id"): ("assessments", "CASCADE"),
    ("entity_signals", "assessment_id"): ("assessments", "CASCADE"),
    ("reports", "assessment_id"): ("assessments", "CASCADE"),
    ("reports", "reporter_user_id"): ("users", "SET NULL"),
    ("reports", "moderator_id"): ("users", "SET NULL"),
    ("llm_calls", "assessment_id"): ("assessments", "SET NULL"),
}

ENUMS = {
    ("users", "role"): ["user", "admin"],
    ("listings", "work_mode"): ["onsite", "remote", "hybrid"],
    ("listings", "employment_type"): ["internship", "full_time", "part_time", "contract"],
    ("listings", "pay_period"): ["month", "year", "one_time"],
    ("listings", "application_channel"): ["email", "website_form", "whatsapp", "telegram", "phone", "linkedin_dm", "unknown"],
    ("listings", "interview_mode"): ["video_call", "in_person", "phone_call", "chat_only", "none"],
    ("assessments", "risk_level"): ["low", "medium", "high"],
    ("assessments", "explanation_source"): ["llm", "template"],
    ("evidence_items", "evidence_type"): ["observed", "model"],
    ("evidence_items", "direction"): ["increases_risk", "decreases_risk"],
    ("entity_signals", "signal_type"): ["email", "email_domain", "phone", "website_domain", "company_name"],
    ("reports", "report_type"): ["advance_fee", "impersonation", "personal_data_request", "fake_company", "harassment", "other"],
    ("reports", "status"): ["pending", "approved", "rejected"],
}

NOT_NULL = {
    "users": {"email", "password_hash", "display_name", "role", "is_active", "created_at"},
    "listings": {"title", "company_name", "description", "work_mode", "employment_type", "pay_period", "currency",
                 "application_channel", "upfront_fee_amount", "interview_mode", "is_synthetic_demo", "created_at"},
    "assessments": {"listing_id", "risk_score", "risk_level", "threshold_low", "threshold_high", "model_version",
                    "explanation_source", "summary", "key_concerns", "what_to_verify", "created_at"},
}
NULLABLE = {
    "listings": {"requirements", "location", "salary_min", "salary_max", "contact_email", "contact_phone", "company_website"},
    "assessments": {"user_id", "owner_token_hash"},
    "evidence_items": {"snippet", "weight"},
    "assessment_checklist_items": {"done_at"},
    "reports": {"reporter_user_id", "moderator_id", "moderator_note", "reviewed_at"},
    "llm_calls": {"assessment_id", "error_code"},
}


def _table(name: str):
    return Base.metadata.tables[name]


def _index_columns(table) -> set[tuple[str, ...]]:
    return {tuple(c.name for c in i.columns) for i in table.indexes}


def test_exactly_eight_tables():
    assert set(Base.metadata.tables) == set(EXPECTED_TABLES)
    assert len(EXPECTED_TABLES) == 8
    assert set(COLUMNS) | set() == set(EXPECTED_TABLES)


@pytest.mark.parametrize("name", EXPECTED_TABLES)
def test_columns_match_section_6(name):
    assert [c.name for c in _table(name).columns] == COLUMNS[name]


@pytest.mark.parametrize("name", EXPECTED_TABLES)
def test_primary_key_is_id(name):
    assert [c.name for c in _table(name).primary_key.columns] == ["id"]


@pytest.mark.parametrize("name", EXPECTED_TABLES)
def test_mysql_table_options(name):
    opts = _table(name).dialect_options["mysql"]
    assert opts["engine"] == "InnoDB"
    assert opts["charset"] == "utf8mb4"
    assert opts["collate"] == "utf8mb4_0900_ai_ci"


@pytest.mark.parametrize("key,expected", FOREIGN_KEYS.items())
def test_foreign_key_targets_and_delete_behavior(key, expected):
    table_name, column = key
    fks = {fk.parent.name: fk for fk in _table(table_name).foreign_keys}
    assert column in fks
    assert fks[column].column.table.name == expected[0]
    assert fks[column].ondelete == expected[1]


def test_no_unexpected_foreign_keys():
    found = {(t.name, fk.parent.name) for t in Base.metadata.tables.values() for fk in t.foreign_keys}
    assert found == set(FOREIGN_KEYS)


@pytest.mark.parametrize("key,values", ENUMS.items())
def test_enum_values_are_the_contract_strings(key, values):
    table_name, column = key
    assert list(_table(table_name).c[column].type.enums) == values


def test_enum_defaults():
    t = _table("users")
    assert t.c.role.server_default.arg == "user"
    l = _table("listings")
    assert l.c.work_mode.server_default.arg == "onsite"
    assert l.c.employment_type.server_default.arg == "internship"
    assert l.c.pay_period.server_default.arg == "month"
    assert l.c.currency.server_default.arg == "INR"
    assert l.c.application_channel.server_default.arg == "unknown"
    assert l.c.interview_mode.server_default.arg == "none"
    assert _table("reports").c.status.server_default.arg == "pending"


@pytest.mark.parametrize("name,cols", NOT_NULL.items())
def test_not_null_columns(name, cols):
    assert all(not _table(name).c[c].nullable for c in cols)


@pytest.mark.parametrize("name,cols", NULLABLE.items())
def test_nullable_columns(name, cols):
    assert all(_table(name).c[c].nullable for c in cols)


def test_unique_constraints():
    assert _table("users").c.email.unique is True
    assert _table("assessments").c.listing_id.unique is True  # 1 listing : 1 assessment

    def unique_sets(table):
        return {tuple(c.name for c in u.columns) for u in table.constraints if u.__class__.__name__ == "UniqueConstraint"}

    assert ("assessment_id", "code") in unique_sets(_table("assessment_checklist_items"))
    assert ("assessment_id", "reporter_key", "report_type") in unique_sets(_table("reports"))


def test_indexes_required_by_section_6():
    assert ("company_name",) in _index_columns(_table("listings"))
    assert ("is_synthetic_demo",) in _index_columns(_table("listings"))
    a = _index_columns(_table("assessments"))
    assert {("user_id",), ("risk_score",), ("risk_level",), ("created_at",)} <= a
    assert ("assessment_id",) in _index_columns(_table("evidence_items"))
    e = _table("entity_signals")
    assert ("assessment_id",) in _index_columns(e)
    assert ("signal_type", "signal_value") in _index_columns(e)
    assert "idx_signal" in {i.name for i in e.indexes}
    r = _index_columns(_table("reports"))
    assert {("assessment_id",), ("status",)} <= r


def test_create_table_sql_for_mysql_has_expected_types():
    dialect = mysql.dialect()
    sql = {t.name: str(CreateTable(t).compile(dialect=dialect)) for t in Base.metadata.sorted_tables}
    assert set(sql) == set(EXPECTED_TABLES)
    joined = "\n".join(sql.values())
    assert "BIGINT UNSIGNED" in joined
    assert "DATETIME(3)" in joined
    assert "CURRENT_TIMESTAMP(3)" in joined
    assert "TINYINT UNSIGNED" in joined
    assert "SMALLINT UNSIGNED" in joined
    assert "DECIMAL(5, 4)" in joined and "DECIMAL(8, 4)" in joined
    assert "JSON" in joined
    assert "utf8mb4_0900_ai_ci" in joined
    # spacing inside ENUM(...) differs between SQLAlchemy versions, so ignore spaces
    assert "ENUM('user','admin')" in sql["users"].replace(" ", "")
    assert "ON DELETE SET NULL" in sql["assessments"]
    assert "ON DELETE CASCADE" in sql["assessments"]
    # Parent tables sort before children, so create_all works in one pass.
    order = [t.name for t in Base.metadata.sorted_tables]
    assert order.index("users") < order.index("assessments") < order.index("evidence_items")
    assert order.index("listings") < order.index("assessments")


def test_init_db_reports_all_eight_tables_present(monkeypatch):
    """init_db() with the engine and create_all replaced: verifies the success path only."""
    from app.db import init_db as mod

    monkeypatch.setattr(mod, "get_engine", lambda: object())
    monkeypatch.setattr(mod.Base.metadata, "create_all", lambda engine: None)
    monkeypatch.setattr(mod, "missing_tables", lambda: [])
    assert mod.init_db() == EXPECTED_TABLES


def test_init_db_failure_message_has_no_password(monkeypatch):
    from sqlalchemy.exc import OperationalError

    from app.db import init_db as mod

    def fail(engine):
        raise OperationalError("CREATE TABLE ...", {}, Exception(1045, "Access denied (using password: YES) test_pw"))

    monkeypatch.setattr(mod, "get_engine", lambda: object())
    monkeypatch.setattr(mod.Base.metadata, "create_all", fail)
    with pytest.raises(mod.DatabaseInitError) as info:
        mod.init_db()
    msg = str(info.value)
    assert "test_pw" not in msg
    assert "MySQL error 1045" in msg


# --------------------------------------------------------------------------
# Phase 2: the same models also work on SQLite (guidebook B8 test database)
# --------------------------------------------------------------------------
def test_sqlite_ddl_has_no_mysql_only_syntax():
    from sqlalchemy.dialects import sqlite

    dialect = sqlite.dialect()
    sql = "\n".join(str(CreateTable(t).compile(dialect=dialect)) for t in Base.metadata.sorted_tables)
    assert "UNSIGNED" not in sql
    assert "CURRENT_TIMESTAMP(3)" not in sql
    assert "DATETIME(3)" not in sql
    assert "CURRENT_TIMESTAMP" in sql


def test_mysql_ddl_is_unchanged_by_the_sqlite_variants():
    sql = {t.name: str(CreateTable(t).compile(dialect=mysql.dialect())) for t in Base.metadata.sorted_tables}
    assert "BIGINT UNSIGNED" in sql["users"] and "AUTO_INCREMENT" in sql["users"]
    assert "DATETIME(3)" in sql["users"]
    assert "CURRENT_TIMESTAMP(3)" in sql["users"]
    assert "INTEGER UNSIGNED" in sql["listings"]  # salary_min / salary_max
    assert "TINYINT UNSIGNED" in sql["evidence_items"]  # severity


def test_sqlite_create_all_and_insert_with_generated_ids():
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all(
            [
                models.User(email="a@example.com", password_hash="h", display_name="A"),
                models.User(email="b@example.com", password_hash="h", display_name="B"),
            ]
        )
        db.commit()
        rows = db.scalars(select(models.User).order_by(models.User.id)).all()
        assert [r.id for r in rows] == [1, 2]  # auto-increment works
        assert rows[0].role == "user" and rows[0].is_active is True  # defaults applied
        assert rows[0].created_at is not None  # server default applied
    engine.dispose()
