"""Community reports and moderation (guidebook Section 5.4, B4, Section 6 `reports`).

    create_report         POST /reports            (anonymous or logged in)
    list_my_reports       GET /reports/mine        (logged in)
    list_admin_reports    GET /admin/reports       (admin)
    moderate_report       PATCH /admin/reports/{id} (admin)

Approved reports are what `report_count_approved` counts (assessment_service),
so approving a report is immediately visible on that assessment.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime

from fastapi import Request
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import AppError, conflict, not_found
from app.db.models import Assessment, Listing, Report, User
from app.schemas.report import (
    AdminReportItem,
    AdminReportPage,
    ReportCreate,
    ReportCreated,
    ReportModerate,
    ReportOut,
)
from app.services.assessment_service import MAX_ID

logger = logging.getLogger("proofhire.reports")


def utc_now() -> datetime:
    """Naive UTC, like every other DATETIME(3) column in this project."""
    return datetime.now(UTC).replace(tzinfo=None)


def client_ip(request: Request) -> str:
    """First value of X-Forwarded-For (Render puts the real client there), else the socket address."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


def reporter_key_for(user: User | None, request: Request) -> str:
    """B4: the user id as text, or sha256(IP + User-Agent) for anonymous reporters (64 hex chars)."""
    if user is not None:
        return str(user.id)
    raw = f"{client_ip(request)}{request.headers.get('user-agent', '')}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _duplicate_exists(db: Session, assessment_id: int, reporter_key: str, report_type: str) -> bool:
    return (
        db.scalar(
            select(Report.id).where(
                Report.assessment_id == assessment_id,
                Report.reporter_key == reporter_key,
                Report.report_type == report_type,
            )
        )
        is not None
    )


# ==================================================================================
# POST /reports
# ==================================================================================
def create_report(db: Session, body: ReportCreate, user: User | None, request: Request) -> ReportCreated:
    """404 unknown assessment, 409 the same reporter already reported it for this type."""
    if not 1 <= body.assessment_id <= MAX_ID or (
        db.scalar(select(Assessment.id).where(Assessment.id == body.assessment_id)) is None
    ):
        raise not_found("Assessment not found")

    key = reporter_key_for(user, request)
    if _duplicate_exists(db, body.assessment_id, key, body.report_type):
        raise conflict("You already reported this assessment for this reason")

    report = Report(
        assessment_id=body.assessment_id,
        reporter_user_id=user.id if user is not None else None,
        reporter_key=key,
        report_type=body.report_type,
        description=body.description,
        status="pending",
    )
    try:
        db.add(report)
        db.commit()
    except IntegrityError:
        # Two identical requests at once: the UNIQUE constraint (uq_report_once) caught the loser.
        db.rollback()
        if _duplicate_exists(db, body.assessment_id, key, body.report_type):
            raise conflict("You already reported this assessment for this reason") from None
        logger.error("Saving a report failed with an integrity error that is not a duplicate")
        raise AppError("internal_error", "Could not save the report", 500) from None
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Saving a report failed: %s", type(exc).__name__)
        raise AppError("internal_error", "Could not save the report", 500) from None

    # Never log the description: it is free text from a user.
    logger.info("Report %s created for assessment %s (type=%s)", report.id, report.assessment_id, report.report_type)
    return ReportCreated(id=report.id, status="pending")


# ==================================================================================
# GET /reports/mine
# ==================================================================================
def list_my_reports(db: Session, user: User) -> list[ReportOut]:
    """The caller's own reports, newest first (reports made anonymously are not linked to an account)."""
    rows = db.scalars(
        select(Report)
        .where(Report.reporter_user_id == user.id)
        .order_by(Report.created_at.desc(), Report.id.desc())
    ).all()
    return [ReportOut.model_validate(r, from_attributes=True) for r in rows]


# ==================================================================================
# GET /admin/reports
# ==================================================================================
def list_admin_reports(db: Session, status: str, page: int, limit: int) -> AdminReportPage:
    """Reports with the given status (default pending), newest first, with the listing title and company."""
    total = db.scalar(select(func.count(Report.id)).where(Report.status == status)) or 0
    rows = db.execute(
        select(Report, Listing.title, Listing.company_name)
        .join(Assessment, Assessment.id == Report.assessment_id)
        .join(Listing, Listing.id == Assessment.listing_id)
        .where(Report.status == status)
        .order_by(Report.created_at.desc(), Report.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    ).all()
    items = [
        AdminReportItem(
            id=r.id,
            assessment_id=r.assessment_id,
            listing_title=title,
            company_name=company,
            report_type=r.report_type,
            description=r.description,
            status=r.status,
            created_at=r.created_at,
        )
        for r, title, company in rows
    ]
    return AdminReportPage(items=items, total=total)


# ==================================================================================
# PATCH /admin/reports/{id}
# ==================================================================================
def moderate_report(db: Session, report_id: int, body: ReportModerate, admin: User) -> ReportOut:
    """Set status (approved|rejected), moderator_id, moderator_note and reviewed_at.

    404 unknown id; 409 if the report was already reviewed. The UPDATE only matches a
    report that is still pending, so two admins deciding at the same moment cannot both win.
    """
    if not 1 <= report_id <= MAX_ID:
        raise not_found("Report not found")
    report = db.scalar(select(Report).where(Report.id == report_id))
    if report is None:
        raise not_found("Report not found")
    if report.status != "pending":
        raise conflict("This report has already been reviewed")

    try:
        result = db.execute(
            update(Report)
            .where(Report.id == report_id, Report.status == "pending")
            .values(
                status=body.status,
                moderator_id=admin.id,
                moderator_note=body.moderator_note,
                reviewed_at=utc_now(),
            )
        )
        if result.rowcount == 0:
            db.rollback()
            raise conflict("This report has already been reviewed")
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Moderating a report failed: %s", type(exc).__name__)
        raise AppError("internal_error", "Could not update the report", 500) from None

    db.refresh(report)
    logger.info("Report %s %s by admin %s", report_id, body.status, admin.id)
    return ReportOut.model_validate(report, from_attributes=True)
