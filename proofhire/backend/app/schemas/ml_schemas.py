"""ML schemas (Member 1 / AI-ML owned). Guidebook Sections 5.1-5.3 and Part A (A11).

Field names, enum values, limits and defaults are frozen by the guidebook.
Do not rename anything here without a docs/CONTRACT_CHANGELOG.md entry.
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

# ---------------------------------------------------------------- 5.1 enums


class WorkMode(str, Enum):
    onsite = "onsite"
    remote = "remote"
    hybrid = "hybrid"


class EmploymentType(str, Enum):
    internship = "internship"
    full_time = "full_time"
    part_time = "part_time"
    contract = "contract"


class PayPeriod(str, Enum):
    month = "month"
    year = "year"
    one_time = "one_time"


class ApplicationChannel(str, Enum):
    email = "email"
    website_form = "website_form"
    whatsapp = "whatsapp"
    telegram = "telegram"
    phone = "phone"
    linkedin_dm = "linkedin_dm"
    unknown = "unknown"


class InterviewMode(str, Enum):
    video_call = "video_call"
    in_person = "in_person"
    phone_call = "phone_call"
    chat_only = "chat_only"
    none = "none"


class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class EvidenceType(str, Enum):
    observed = "observed"
    model = "model"


class EvidenceDirection(str, Enum):
    increases_risk = "increases_risk"
    decreases_risk = "decreases_risk"


class ExplanationSource(str, Enum):
    llm = "llm"
    template = "template"


class SignalType(str, Enum):
    email = "email"
    email_domain = "email_domain"
    phone = "phone"
    website_domain = "website_domain"
    company_name = "company_name"


# ------------------------------------------------------- 5.2 ListingInput

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^[0-9\s+\-()]+$")


class ListingInput(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    company_name: str = Field(min_length=2, max_length=200)
    description: str = Field(min_length=20, max_length=8000)
    requirements: Optional[str] = Field(default=None, max_length=4000)
    location: Optional[str] = Field(default=None, max_length=200)
    work_mode: WorkMode = WorkMode.onsite
    employment_type: EmploymentType = EmploymentType.internship
    salary_min: Optional[int] = Field(default=None, ge=0)
    salary_max: Optional[int] = Field(default=None, ge=0)
    pay_period: PayPeriod = PayPeriod.month
    currency: str = Field(default="INR", min_length=3, max_length=3)
    contact_email: Optional[str] = Field(default=None, max_length=255)
    contact_phone: Optional[str] = Field(default=None, max_length=32)
    application_channel: ApplicationChannel = ApplicationChannel.unknown
    company_website: Optional[str] = Field(default=None, max_length=500)
    upfront_fee_amount: int = Field(default=0, ge=0)
    interview_mode: InterviewMode = InterviewMode.none

    @field_validator("contact_email")
    @classmethod
    def _check_email(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not _EMAIL_RE.match(v):
            raise ValueError("must be a valid email address")
        return v

    @field_validator("contact_phone")
    @classmethod
    def _check_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not _PHONE_RE.match(v):
            raise ValueError("may contain only digits, spaces, +, -, ( and )")
        return v

    @field_validator("company_website")
    @classmethod
    def _check_website(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("must start with http:// or https://")
        return v

    @model_validator(mode="after")
    def _check_salary(self) -> "ListingInput":
        if (
            self.salary_min is not None
            and self.salary_max is not None
            and self.salary_max < self.salary_min
        ):
            raise ValueError("salary_max must be >= salary_min")
        return self


# ------------------------------------------------ 5.3 result building blocks


class Thresholds(BaseModel):
    low: float
    high: float


class EvidenceItem(BaseModel):
    id: str
    code: str
    label: str
    type: EvidenceType
    direction: EvidenceDirection
    severity: int = Field(ge=1, le=3)
    snippet: Optional[str] = None
    weight: Optional[float] = None


class KeyConcern(BaseModel):
    text: str
    evidence_ids: list[str]


class Explanation(BaseModel):
    source: ExplanationSource
    summary: str
    key_concerns: list[KeyConcern] = Field(default_factory=list)
    what_to_verify: list[str] = Field(default_factory=list)


class ChecklistItem(BaseModel):
    """ML-built checklist item (no id; backend stores and assigns ids)."""

    code: str
    text: str
    priority: int
    done: bool = False


class Entity(BaseModel):
    type: SignalType
    value: str


class LlmMeta(BaseModel):
    provider: str  # groq / openrouter / template
    model: str
    latency_ms: int = Field(ge=0)
    success: bool
    error_code: Optional[str] = None


class MlResult(BaseModel):
    """Output of assess_listing(): Section 5.3 without DB fields, plus llm_meta."""

    risk_score: float = Field(ge=0.0, le=1.0)
    risk_level: RiskLevel
    thresholds: Thresholds
    model_version: str
    evidence: list[EvidenceItem]
    explanation: Explanation
    checklist: list[ChecklistItem]
    entities: list[Entity]
    llm_meta: LlmMeta


# Section 5.3 full response (backend completes it). Provided so the shape is
# published once; backend may import instead of redefining.
class AssessmentChecklistItem(ChecklistItem):
    id: int


class Connection(BaseModel):
    signal_type: SignalType
    value_masked: str
    times_seen: int
    high_risk_count: int


class AssessmentResult(BaseModel):
    assessment_id: int
    created_at: str
    listing: ListingInput
    risk_score: float
    risk_level: RiskLevel
    thresholds: Thresholds
    model_version: str
    evidence: list[EvidenceItem]
    explanation: Explanation
    checklist: list[AssessmentChecklistItem]
    entities: list[Entity]
    connections: list[Connection] = Field(default_factory=list)
    report_count_approved: int = 0
    owner_token: Optional[str] = None
    disclaimer: str = "ProofHire gives a risk estimate, not a verification of the employer."


# ------------------------------------------------- A11 endpoint responses


class MlHealthResponse(BaseModel):
    loaded: bool
    model_version: Optional[str] = None
    trained_at: Optional[str] = None
    sklearn_version: Optional[str] = None
    llm_enabled: bool
    llm_circuit_open: bool


class PredictResponse(BaseModel):
    risk_score: float
    risk_level: RiskLevel
    thresholds: Thresholds
    model_version: str


class EvidenceResponse(BaseModel):
    risk_score: float
    risk_level: RiskLevel
    evidence: list[EvidenceItem]


class ExtractEntitiesResponse(BaseModel):
    entities: list[Entity]


class ReloadResponse(BaseModel):
    reloaded: bool
    model_version: str
    sha256: str
