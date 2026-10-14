"""The eight ORM tables of guidebook Section 6 (MySQL 8.4, InnoDB, utf8mb4).

Frozen contract: table names, column names, types, enums, keys, indexes and
delete behaviour follow Section 6 exactly. Do not rename anything here without
the team agreeing and a line in docs/CONTRACT_CHANGELOG.md.

Delete behaviour (Section 6):
  * child tables use ON DELETE CASCADE
  * SET NULL only where Section 6 says so: assessments.user_id,
    reports.reporter_user_id, reports.moderator_id, llm_calls.assessment_id
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    DECIMAL,
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text as sql_text,  # NOT plain "text": AssessmentChecklistItem has a column named text
)
from sqlalchemy.dialects import mysql
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.expression import FunctionElement
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import MYSQL_TABLE_OPTIONS, Base

# --------------------------------------------------------------------------
# Section 5.1 enumerations: literal strings, used everywhere.
# --------------------------------------------------------------------------
USER_ROLES = ("user", "admin")
WORK_MODES = ("onsite", "remote", "hybrid")
EMPLOYMENT_TYPES = ("internship", "full_time", "part_time", "contract")
PAY_PERIODS = ("month", "year", "one_time")
APPLICATION_CHANNELS = ("email", "website_form", "whatsapp", "telegram", "phone", "linkedin_dm", "unknown")
INTERVIEW_MODES = ("video_call", "in_person", "phone_call", "chat_only", "none")
RISK_LEVELS = ("low", "medium", "high")
EVIDENCE_TYPES = ("observed", "model")
EVIDENCE_DIRECTIONS = ("increases_risk", "decreases_risk")
EXPLANATION_SOURCES = ("llm", "template")
REPORT_TYPES = ("advance_fee", "impersonation", "personal_data_request", "fake_company", "harassment", "other")
REPORT_STATUSES = ("pending", "approved", "rejected")
SIGNAL_TYPES = ("email", "email_domain", "phone", "website_domain", "company_name")


def _enum(name: str, values: tuple[str, ...]) -> Enum:
    # Native MySQL ENUM; validate_strings rejects values outside the contract.
    return Enum(*values, name=name, validate_strings=True)


# --------------------------------------------------------------------------
# Column types. Primary keys are BIGINT UNSIGNED AUTO_INCREMENT; timestamps
# are DATETIME(3) in UTC with DEFAULT CURRENT_TIMESTAMP(3).
#
# Production is MySQL 8.4, so the MySQL types below are exactly what Section 6
# asks for. Each one also has a plain variant for SQLite, which the guidebook
# (B8) uses for the in-memory test database. The variants only apply when the
# dialect is SQLite; the MySQL DDL is unchanged.
# --------------------------------------------------------------------------
BIGINT_U = (
    BigInteger()
    .with_variant(mysql.BIGINT(unsigned=True), "mysql")
    # SQLite only auto-increments a column declared exactly INTEGER.
    .with_variant(Integer(), "sqlite")
)
INT_U = Integer().with_variant(mysql.INTEGER(unsigned=True), "mysql")
SMALLINT_U = SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql")
TINYINT_U = SmallInteger().with_variant(mysql.TINYINT(unsigned=True), "mysql")
DATETIME3 = DateTime().with_variant(mysql.DATETIME(fsp=3), "mysql")


class _Now3(FunctionElement):
    """Server-side "now" default: CURRENT_TIMESTAMP(3) on MySQL, CURRENT_TIMESTAMP elsewhere.

    SQLite does not understand CURRENT_TIMESTAMP(3), so the SQL differs per dialect.
    """

    type = DateTime()
    inherit_cache = True


@compiles(_Now3)
def _now3_default(element, compiler, **kw):  # noqa: ARG001
    return "CURRENT_TIMESTAMP"


@compiles(_Now3, "mysql")
def _now3_mysql(element, compiler, **kw):  # noqa: ARG001
    return "CURRENT_TIMESTAMP(3)"


NOW3 = _Now3()


def _table_args(*extra) -> tuple:
    """Table-level constraints/indexes followed by the MySQL options dict."""
    return (*extra, dict(MYSQL_TABLE_OPTIONS))


# --------------------------------------------------------------------------
# users
# --------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"
    __table_args__ = _table_args()

    id: Mapped[int] = mapped_column(BIGINT_U, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)  # lower-cased before insert
    password_hash: Mapped[str] = mapped_column(String(255))  # bcrypt
    display_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(_enum("user_role", USER_ROLES), default="user", server_default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=sql_text("1"))
    created_at: Mapped[datetime] = mapped_column(DATETIME3, server_default=NOW3)


# --------------------------------------------------------------------------
# listings
# --------------------------------------------------------------------------
class Listing(Base):
    __tablename__ = "listings"
    __table_args__ = _table_args()

    id: Mapped[int] = mapped_column(BIGINT_U, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200))
    company_name: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str] = mapped_column(Text)  # max 8000 chars enforced in the API
    requirements: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(200))
    work_mode: Mapped[str] = mapped_column(_enum("work_mode", WORK_MODES), default="onsite", server_default="onsite")
    employment_type: Mapped[str] = mapped_column(
        _enum("employment_type", EMPLOYMENT_TYPES), default="internship", server_default="internship"
    )
    salary_min: Mapped[int | None] = mapped_column(INT_U)
    salary_max: Mapped[int | None] = mapped_column(INT_U)
    pay_period: Mapped[str] = mapped_column(_enum("pay_period", PAY_PERIODS), default="month", server_default="month")
    currency: Mapped[str] = mapped_column(CHAR(3), default="INR", server_default="INR")
    contact_email: Mapped[str | None] = mapped_column(String(255))
    contact_phone: Mapped[str | None] = mapped_column(String(32))
    application_channel: Mapped[str] = mapped_column(
        _enum("application_channel", APPLICATION_CHANNELS), default="unknown", server_default="unknown"
    )
    company_website: Mapped[str | None] = mapped_column(String(500))
    upfront_fee_amount: Mapped[int] = mapped_column(INT_U, default=0, server_default=sql_text("0"))
    interview_mode: Mapped[str] = mapped_column(
        _enum("interview_mode", INTERVIEW_MODES), default="none", server_default="none"
    )
    is_synthetic_demo: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sql_text("0"), index=True)
    created_at: Mapped[datetime] = mapped_column(DATETIME3, server_default=NOW3)

    assessment: Mapped["Assessment | None"] = relationship(
        back_populates="listing", uselist=False, cascade="all, delete-orphan", passive_deletes=True
    )


# --------------------------------------------------------------------------
# assessments
# --------------------------------------------------------------------------
class Assessment(Base):
    __tablename__ = "assessments"
    __table_args__ = _table_args()

    id: Mapped[int] = mapped_column(BIGINT_U, primary_key=True, autoincrement=True)
    # NULL = anonymous assessment; deleting the user keeps the assessment.
    user_id: Mapped[int | None] = mapped_column(
        BIGINT_U, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    # 1 listing : 1 assessment
    listing_id: Mapped[int] = mapped_column(
        BIGINT_U, ForeignKey("listings.id", ondelete="CASCADE"), unique=True
    )
    owner_token_hash: Mapped[str | None] = mapped_column(CHAR(64))  # sha256 of the anonymous owner token
    risk_score: Mapped[Decimal] = mapped_column(DECIMAL(5, 4), index=True)
    risk_level: Mapped[str] = mapped_column(_enum("risk_level", RISK_LEVELS), index=True)
    threshold_low: Mapped[Decimal] = mapped_column(DECIMAL(5, 4))  # copied from model_meta at scoring time
    threshold_high: Mapped[Decimal] = mapped_column(DECIMAL(5, 4))
    model_version: Mapped[str] = mapped_column(String(64))
    explanation_source: Mapped[str] = mapped_column(_enum("explanation_source", EXPLANATION_SOURCES))
    summary: Mapped[str] = mapped_column(Text)  # explanation.summary
    key_concerns: Mapped[list] = mapped_column(JSON)  # list of {text, evidence_ids}
    what_to_verify: Mapped[list] = mapped_column(JSON)  # list of strings
    created_at: Mapped[datetime] = mapped_column(DATETIME3, server_default=NOW3, index=True)

    listing: Mapped[Listing] = relationship(back_populates="assessment")
    evidence_items: Mapped[list["EvidenceItem"]] = relationship(
        back_populates="assessment",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="EvidenceItem.sort_order",
    )
    checklist_items: Mapped[list["AssessmentChecklistItem"]] = relationship(
        back_populates="assessment",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AssessmentChecklistItem.priority, AssessmentChecklistItem.id",
    )
    entity_signals: Mapped[list["EntitySignal"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan", passive_deletes=True
    )
    reports: Mapped[list["Report"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan", passive_deletes=True
    )
    # llm_calls.assessment_id is SET NULL: the log rows outlive the assessment,
    # so no delete cascade here (the database does the SET NULL).
    llm_calls: Mapped[list["LlmCall"]] = relationship(back_populates="assessment", passive_deletes=True)


# --------------------------------------------------------------------------
# evidence_items
# --------------------------------------------------------------------------
class EvidenceItem(Base):
    __tablename__ = "evidence_items"
    __table_args__ = _table_args()

    id: Mapped[int] = mapped_column(BIGINT_U, primary_key=True, autoincrement=True)
    assessment_id: Mapped[int] = mapped_column(
        BIGINT_U, ForeignKey("assessments.id", ondelete="CASCADE"), index=True
    )
    public_id: Mapped[str] = mapped_column(String(8))  # E1, E2 ... as returned by ML
    code: Mapped[str] = mapped_column(String(64))  # e.g. UPFRONT_FEE, MODEL_TERM
    label: Mapped[str] = mapped_column(String(255))
    evidence_type: Mapped[str] = mapped_column(_enum("evidence_type", EVIDENCE_TYPES))
    direction: Mapped[str] = mapped_column(_enum("evidence_direction", EVIDENCE_DIRECTIONS))
    severity: Mapped[int] = mapped_column(TINYINT_U)  # 1 to 3
    snippet: Mapped[str | None] = mapped_column(String(500))  # exact span from the listing
    weight: Mapped[Decimal | None] = mapped_column(DECIMAL(8, 4))  # NULL for observed evidence
    sort_order: Mapped[int] = mapped_column(SMALLINT_U)  # order returned by ML

    assessment: Mapped[Assessment] = relationship(back_populates="evidence_items")


# --------------------------------------------------------------------------
# assessment_checklist_items
# --------------------------------------------------------------------------
class AssessmentChecklistItem(Base):
    __tablename__ = "assessment_checklist_items"
    # UNIQUE(assessment_id, code) also serves as the assessment_id index
    # (assessment_id is its leftmost column), so no separate index is added.
    __table_args__ = _table_args(UniqueConstraint("assessment_id", "code", name="uq_checklist_assessment_code"))

    id: Mapped[int] = mapped_column(BIGINT_U, primary_key=True, autoincrement=True)
    assessment_id: Mapped[int] = mapped_column(BIGINT_U, ForeignKey("assessments.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(64))  # from checklist_library.json
    text: Mapped[str] = mapped_column(String(500))
    priority: Mapped[int] = mapped_column(TINYINT_U)  # 1 = most important
    is_done: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sql_text("0"))
    done_at: Mapped[datetime | None] = mapped_column(DATETIME3)

    assessment: Mapped[Assessment] = relationship(back_populates="checklist_items")


# --------------------------------------------------------------------------
# entity_signals
# --------------------------------------------------------------------------
class EntitySignal(Base):
    __tablename__ = "entity_signals"
    # Composite index used by the connections query (B6).
    __table_args__ = _table_args(Index("idx_signal", "signal_type", "signal_value"))

    id: Mapped[int] = mapped_column(BIGINT_U, primary_key=True, autoincrement=True)
    assessment_id: Mapped[int] = mapped_column(
        BIGINT_U, ForeignKey("assessments.id", ondelete="CASCADE"), index=True
    )
    signal_type: Mapped[str] = mapped_column(_enum("signal_type", SIGNAL_TYPES))
    # Normalised: lower-case, digits-only phone. Free-mail domains are never
    # stored as email_domain / website_domain (enforced by the service layer).
    signal_value: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DATETIME3, server_default=NOW3)

    assessment: Mapped[Assessment] = relationship(back_populates="entity_signals")


# --------------------------------------------------------------------------
# reports
# --------------------------------------------------------------------------
class Report(Base):
    __tablename__ = "reports"
    # Blocks duplicate reports (the API turns the violation into 409).
    __table_args__ = _table_args(
        UniqueConstraint("assessment_id", "reporter_key", "report_type", name="uq_report_once")
    )

    id: Mapped[int] = mapped_column(BIGINT_U, primary_key=True, autoincrement=True)
    assessment_id: Mapped[int] = mapped_column(
        BIGINT_U, ForeignKey("assessments.id", ondelete="CASCADE"), index=True
    )
    reporter_user_id: Mapped[int | None] = mapped_column(BIGINT_U, ForeignKey("users.id", ondelete="SET NULL"))
    # user id as text, or sha256(IP + UA) for anonymous reporters
    reporter_key: Mapped[str] = mapped_column(String(64))
    report_type: Mapped[str] = mapped_column(_enum("report_type", REPORT_TYPES))
    description: Mapped[str] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(
        _enum("report_status", REPORT_STATUSES), default="pending", server_default="pending", index=True
    )
    moderator_id: Mapped[int | None] = mapped_column(BIGINT_U, ForeignKey("users.id", ondelete="SET NULL"))
    moderator_note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DATETIME3, server_default=NOW3)
    reviewed_at: Mapped[datetime | None] = mapped_column(DATETIME3)

    assessment: Mapped[Assessment] = relationship(back_populates="reports")


# --------------------------------------------------------------------------
# llm_calls
# --------------------------------------------------------------------------
class LlmCall(Base):
    __tablename__ = "llm_calls"
    __table_args__ = _table_args()

    id: Mapped[int] = mapped_column(BIGINT_U, primary_key=True, autoincrement=True)
    assessment_id: Mapped[int | None] = mapped_column(BIGINT_U, ForeignKey("assessments.id", ondelete="SET NULL"))
    provider: Mapped[str] = mapped_column(String(32))  # groq / openrouter / template
    model: Mapped[str] = mapped_column(String(100))
    latency_ms: Mapped[int] = mapped_column(INT_U)
    success: Mapped[bool] = mapped_column(Boolean)
    error_code: Mapped[str | None] = mapped_column(String(64))  # timeout, http_429, bad_json, ...
    created_at: Mapped[datetime] = mapped_column(DATETIME3, server_default=NOW3)

    assessment: Mapped[Assessment | None] = relationship(back_populates="llm_calls")
