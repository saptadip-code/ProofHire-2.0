"""GET /admin/reports and PATCH /admin/reports/{id} (guidebook Section 5.4 and B4). Admin only."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_admin
from app.db.models import User
from app.schemas.report import AdminReportPage, ReportModerate, ReportOut, ReportStatus
from app.services import report_service

router = APIRouter(prefix="/admin", tags=["admin"])

_ADMIN_ERRORS = {
    401: {"description": "unauthorized: missing, invalid or expired token"},
    403: {"description": "forbidden: the caller is not an administrator"},
}


@router.get(
    "/reports",
    response_model=AdminReportPage,
    responses=_ADMIN_ERRORS,
    summary="Moderation queue (admin only)",
)
def list_reports(
    status: ReportStatus = Query("pending"),
    page: int = Query(1, ge=1, le=1_000_000),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> AdminReportPage:
    return report_service.list_admin_reports(db, status, page, limit)


@router.patch(
    "/reports/{report_id}",
    response_model=ReportOut,
    responses={
        **_ADMIN_ERRORS,
        404: {"description": "not_found: unknown report"},
        409: {"description": "conflict: the report was already approved or rejected"},
        422: {"description": "validation_error: status must be 'approved' or 'rejected'; note max 500 chars"},
    },
    summary="Approve or reject a report (admin only)",
)
def moderate_report(
    report_id: int,
    body: ReportModerate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> ReportOut:
    return report_service.moderate_report(db, report_id, body, admin)
