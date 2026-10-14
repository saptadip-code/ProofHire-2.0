"""Request and response models for /assessments (guidebook Sections 5.2, 5.3, 5.4 and B4).

    ListingInput        POST body, validated exactly as Section 5.2
    AssessmentResult    response of POST (201) and GET /assessments/{id}  (Section 5.3)
    AssessmentCreated   AssessmentResult + owner_token (anonymous callers, creation response only)
    AssessmentPage      response of GET /assessments (items are AssessmentSummary)

NOTE on ownership of ListingInput: the guidebook (A2) says Member 1's
schemas/ml_schemas.py also defines ListingInput. The backend must validate the
request itself (Section 5.2 is a frozen shared contract), so this module has its
own copy of that contract. app/services/ml_gateway.py converts it to Member 1's
class when it calls the pipeline, so the two never have to be the same object.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Literal, Union

from pydantic import (
    BaseModel,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    ValidationInfo,
    field_serializer,
    field_validator,
)

# ---- Section 5.1 enumerations (literal strings) --------------------------------
WorkMode = Literal["onsite", "remote", "hybrid"]
EmploymentType = Literal["internship", "full_time", "part_time", "contract"]
PayPeriod = Literal["month", "year", "one_time"]
ApplicationChannel = Literal["email", "website_form", "whatsapp", "telegram", "phone", "linkedin_dm", "unknown"]
InterviewMode = Literal["video_call", "in_person", "phone_call", "chat_only", "none"]
RiskLevel = Literal["low", "medium", "high"]
EvidenceType = Literal["observed", "model"]
EvidenceDirection = Literal["increases_risk", "decreases_risk"]
ExplanationSource = Literal["llm", "template"]
SignalType = Literal["email", "email_domain", "phone", "website_domain", "company_name"]

DISCLAIMER = "ProofHire gives a risk estimate, not a verification of the employer."

# Section 6 stores money as INT UNSIGNED. Section 5.2 only says ">= 0"; without an
# upper bound a huge number would pass validation and then fail inside MySQL (500).
UINT32_MAX = 4_294_967_295

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")  # Section 5.2
_PHONE_RE = re.compile(r"^[0-9 +\-()]+$")  # digits, spaces, +, -, (, )
_CURRENCY_RE = re.compile(r"^[A-Za-z]{3}$")


def _strip(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


def _blank_to_none(value: object) -> object:
    """Trim; an empty optional text field means "not given" (the frontend sends null)."""
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _iso_utc(value: datetime) -> str:
    """ISO-8601 UTC string like 2026-10-12T09:30:11Z. Database times are naive UTC."""
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc)
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


# ==================================================================================
# 5.2 ListingInput (request body)
# ==================================================================================
class ListingInput(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    company_name: str = Field(min_length=2, max_length=200)
    description: str = Field(min_length=20, max_length=8000)
    requirements: str | None = Field(default=None, max_length=4000)
    location: str | None = Field(default=None, max_length=200)
    work_mode: WorkMode = "onsite"
    employment_type: EmploymentType = "internship"
    salary_min: int | None = Field(default=None, ge=0, le=UINT32_MAX)
    salary_max: int | None = Field(default=None, ge=0, le=UINT32_MAX)
    pay_period: PayPeriod = "month"
    currency: str = "INR"
    contact_email: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=32)
    application_channel: ApplicationChannel = "unknown"
    company_website: str | None = Field(default=None, max_length=500)
    upfront_fee_amount: int = Field(default=0, ge=0, le=UINT32_MAX)
    interview_mode: InterviewMode = "none"

    @field_validator("title", "company_name", "description", "currency", mode="before")
    @classmethod
    def _trim_required(cls, v: object) -> object:
        return _strip(v)

    @field_validator("requirements", "location", "contact_email", "contact_phone", "company_website", mode="before")
    @classmethod
    def _trim_optional(cls, v: object) -> object:
        return _blank_to_none(v)

    @field_validator("currency")
    @classmethod
    def _currency(cls, v: str) -> str:
        if not _CURRENCY_RE.match(v):
            raise ValueError("must be a 3-letter currency code")
        return v.upper()

    @field_validator("contact_email")
    @classmethod
    def _email(cls, v: str | None) -> str | None:
        if v is not None and not _EMAIL_RE.match(v):
            raise ValueError("must be a valid email address")
        return v

    @field_validator("contact_phone")
    @classmethod
    def _phone(cls, v: str | None) -> str | None:
        if v is not None and not _PHONE_RE.match(v):
            raise ValueError("may contain only digits, spaces, +, -, ( and )")
        return v

    @field_validator("company_website")
    @classmethod
    def _website(cls, v: str | None) -> str | None:
        if v is not None and not v.lower().startswith(("http://", "https://")):
            raise ValueError("must start with http:// or https://")
        return v

    @field_validator("salary_max")
    @classmethod
    def _salary_order(cls, v: int | None, info: ValidationInfo) -> int | None:
        low = info.data.get("salary_min")  # salary_min is declared first
        if v is not None and low is not None and v < low:
            raise ValueError("must be >= salary_min")
        return v


# ==================================================================================
# 5.3 AssessmentResult (response)
# ==================================================================================
class ListingEcho(BaseModel):
    """The listing as stored, echoed back. No validators: for viewers who are not
    the owner, contact_email / contact_phone are masked and would not pass the
    ListingInput patterns."""

    title: str
    company_name: str
    description: str
    requirements: str | None
    location: str | None
    work_mode: WorkMode
    employment_type: EmploymentType
    salary_min: int | None
    salary_max: int | None
    pay_period: PayPeriod
    currency: str
    contact_email: str | None
    contact_phone: str | None
    application_channel: ApplicationChannel
    company_website: str | None
    upfront_fee_amount: int
    interview_mode: InterviewMode


class Thresholds(BaseModel):
    low: float
    high: float


class EvidenceOut(BaseModel):
    id: str  # E1, E2 ... (evidence_items.public_id)
    code: str
    label: str
    type: EvidenceType
    direction: EvidenceDirection
    severity: int
    snippet: str | None
    weight: float | None


class KeyConcern(BaseModel):
    text: str
    evidence_ids: list[str]


class ExplanationOut(BaseModel):
    source: ExplanationSource
    summary: str
    key_concerns: list[KeyConcern]
    what_to_verify: list[str]


class ChecklistItemOut(BaseModel):
    id: int
    code: str
    text: str
    priority: int
    done: bool


class EntityOut(BaseModel):
    type: SignalType
    value: str


class ConnectionOut(BaseModel):
    signal_type: SignalType
    value_masked: str
    times_seen: int
    high_risk_count: int


class AssessmentResult(BaseModel):
    assessment_id: int
    created_at: datetime
    listing: ListingEcho
    risk_score: float
    risk_level: RiskLevel
    thresholds: Thresholds
    model_version: str
    evidence: list[EvidenceOut]
    explanation: ExplanationOut
    checklist: list[ChecklistItemOut]
    entities: list[EntityOut]
    connections: list[ConnectionOut]
    report_count_approved: int
    disclaimer: str = DISCLAIMER

    @field_serializer("created_at")
    def _ser_created_at(self, value: datetime) -> str:
        return _iso_utc(value)


class AssessmentCreated(AssessmentResult):
    """Creation response for ANONYMOUS callers only. The raw token appears here and
    nowhere else; only its SHA-256 hash is stored."""

    owner_token: str


# ==================================================================================
# GET /assessments (list)
# ==================================================================================
class AssessmentSummary(BaseModel):
    id: int
    created_at: datetime
    title: str
    company_name: str
    risk_score: float
    risk_level: RiskLevel
    evidence_count: int
    report_count_approved: int

    @field_serializer("created_at")
    def _ser_created_at(self, value: datetime) -> str:
        return _iso_utc(value)


class AssessmentPage(BaseModel):
    items: list[AssessmentSummary]
    total: int
    page: int
    limit: int


# ==================================================================================
# PATCH /assessments/{id}/checklist/{item_id}   (Section 5.4, B4)
# ==================================================================================
class ChecklistPatch(BaseModel):
    """Request body {done: bool}. StrictBool: "yes", 1 or "true" are rejected (422)."""

    done: StrictBool


class ChecklistPatchResult(BaseModel):
    """Response {id, done}."""

    id: int
    done: bool


# ==================================================================================
# POST /assessments/compare   (Section 5.4, B4)
# ==================================================================================
class CompareRequest(BaseModel):
    """Request body {assessment_id_a, assessment_id_b}. The two ids must differ (400)."""

    assessment_id_a: int
    assessment_id_b: int


# A row value is a plain JSON scalar (number, text, true/false or null).
CompareValue = Union[StrictBool, StrictInt, StrictFloat, StrictStr, None]


class CompareRow(BaseModel):
    signal: str
    a: CompareValue
    b: CompareValue
    better: Literal["a", "b", "tie"]  # lower risk wins


class CompareResult(BaseModel):
    a: AssessmentSummary
    b: AssessmentSummary
    rows: list[CompareRow]
