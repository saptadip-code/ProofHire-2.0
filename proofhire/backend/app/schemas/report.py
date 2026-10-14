"""Request and response models for /reports and /admin/reports (guidebook Section 5.4 and B4).

    ReportCreate      POST /reports body  {assessment_id, report_type, description (10-1000)}
    ReportCreated     201 response        {id, status: 'pending'}
    ReportOut         one report          {id, assessment_id, report_type, description, status,
                                           moderator_note, created_at}   (GET /reports/mine items,
                                           and the PATCH /admin/reports/{id} response)
    AdminReportItem   GET /admin/reports  {id, assessment_id, listing_title, company_name,
                                           report_type, description, status, created_at}
    AdminReportPage   GET /admin/reports  {items, total}
    ReportModerate    PATCH body          {status: 'approved'|'rejected', moderator_note (max 500)}

No field outside these lists exists: the contract (B4) is frozen.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, StrictInt, field_serializer, field_validator

from app.schemas.assessment import _iso_utc

# Section 5.1
ReportType = Literal["advance_fee", "impersonation", "personal_data_request", "fake_company", "harassment", "other"]
ReportStatus = Literal["pending", "approved", "rejected"]
ModerationStatus = Literal["approved", "rejected"]  # a moderator can only decide, never set 'pending'


class ReportCreate(BaseModel):
    # StrictInt: "7", 7.5 or true is not an assessment id. An integer that matches no assessment
    # (0, negative, or beyond BIGINT) is a 404 from the service, like the other /assessments routes.
    assessment_id: StrictInt
    report_type: ReportType
    # Length is measured AFTER trimming, so ten spaces do not count as a description.
    description: str = Field(min_length=10, max_length=1000)

    @field_validator("description", mode="before")
    @classmethod
    def _trim(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v


class ReportCreated(BaseModel):
    id: int
    status: Literal["pending"] = "pending"


class ReportOut(BaseModel):
    id: int
    assessment_id: int
    report_type: ReportType
    description: str
    status: ReportStatus
    moderator_note: str | None
    created_at: datetime

    @field_serializer("created_at")
    def _ser_created_at(self, value: datetime) -> str:
        return _iso_utc(value)


class AdminReportItem(BaseModel):
    id: int
    assessment_id: int
    listing_title: str
    company_name: str
    report_type: ReportType
    description: str
    status: ReportStatus
    created_at: datetime

    @field_serializer("created_at")
    def _ser_created_at(self, value: datetime) -> str:
        return _iso_utc(value)


class AdminReportPage(BaseModel):
    items: list[AdminReportItem]
    total: int


class ReportModerate(BaseModel):
    status: ModerationStatus
    moderator_note: str | None = Field(default=None, max_length=500)

    @field_validator("moderator_note", mode="before")
    @classmethod
    def _trim_note(cls, v: object) -> object:
        """Trim; a blank note means "no note" (stored as NULL)."""
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v
