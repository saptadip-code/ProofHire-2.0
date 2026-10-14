"""POST /reports and GET /reports/mine (guidebook Section 5.4 and B4)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, get_optional_user
from app.db.models import User
from app.schemas.report import ReportCreate, ReportCreated, ReportOut
from app.services import report_service

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post(
    "",
    status_code=201,
    response_model=ReportCreated,
    responses={
        401: {"description": "unauthorized: an Authorization header was sent but the token is invalid or expired"},
        404: {"description": "not_found: unknown assessment"},
        409: {"description": "conflict: this reporter already reported this assessment for this report_type"},
        422: {"description": "validation_error: bad report_type or description not 10-1000 characters"},
    },
    summary="Report a suspicious listing (anonymous or logged in)",
)
def create_report(
    body: ReportCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> ReportCreated:
    return report_service.create_report(db, body, user, request)


@router.get(
    "/mine",
    response_model=list[ReportOut],
    responses={401: {"description": "unauthorized: login required"}},
    summary="My reports (login required)",
)
def my_reports(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[ReportOut]:
    return report_service.list_my_reports(db, user)
