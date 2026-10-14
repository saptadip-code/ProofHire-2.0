"""POST/GET /assessments, GET/DELETE /assessments/{id}, PATCH checklist, POST compare
(guidebook Section 5.4 and B4).

Plain `def` routes: FastAPI runs them in a worker thread, so the ML call (which
may wait for an LLM) and the database work never block the event loop (B4).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, get_optional_user
from app.db.models import User
from app.schemas.assessment import (
    AssessmentCreated,
    AssessmentPage,
    AssessmentResult,
    ChecklistPatch,
    ChecklistPatchResult,
    CompareRequest,
    CompareResult,
    ListingInput,
    RiskLevel,
)
from app.services import assessment_service, compare_service

router = APIRouter(prefix="/assessments", tags=["assessments"])

_OWNER_HEADER = Header(
    default=None,
    alias="X-Owner-Token",
    description="The owner_token returned when an anonymous assessment was created.",
)


@router.post(
    "",
    status_code=201,
    # response_model=None on purpose: the same route answers with AssessmentCreated (anonymous,
    # includes owner_token) or AssessmentResult (logged in, no owner_token key at all).
    response_model=None,
    responses={
        201: {"model": AssessmentCreated, "description": "owner_token is present for anonymous callers only"},
        401: {"description": "An Authorization header was sent but the token is invalid or expired"},
        422: {"description": "validation_error"},
        503: {"description": "model_unavailable: the ML model is not loaded"},
    },
    summary="Assess a job listing (anonymous or logged in)",
)
def create_assessment(
    body: ListingInput,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    return assessment_service.create_assessment(db, body, user)


@router.get("", response_model=AssessmentPage, summary="My saved assessments (login required)")
def list_assessments(
    page: int = Query(1, ge=1, le=1_000_000),
    limit: int = Query(20, ge=1, le=50),
    risk_level: RiskLevel | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AssessmentPage:
    return assessment_service.list_assessments(db, user, page, limit, risk_level)


@router.post(
    "/compare",
    response_model=CompareResult,
    responses={
        400: {"description": "bad_request: the two ids are equal"},
        404: {"description": "not_found: one of the assessments does not exist"},
    },
    summary="Compare two assessments side by side (public)",
)
def compare_assessments(body: CompareRequest, db: Session = Depends(get_db)) -> CompareResult:
    return compare_service.compare_assessments(db, body.assessment_id_a, body.assessment_id_b)


@router.get(
    "/{assessment_id}",
    response_model=AssessmentResult,
    summary="One assessment (contact details only for the owner)",
)
def get_assessment(
    assessment_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
    x_owner_token: str | None = _OWNER_HEADER,
) -> AssessmentResult:
    return assessment_service.get_assessment(db, assessment_id, user, x_owner_token)


@router.delete(
    "/{assessment_id}",
    status_code=204,
    response_class=Response,
    summary="Delete my assessment (owner only)",
)
def delete_assessment(
    assessment_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
    x_owner_token: str | None = _OWNER_HEADER,
) -> Response:
    assessment_service.delete_assessment(db, assessment_id, user, x_owner_token)
    return Response(status_code=204)


@router.patch(
    "/{assessment_id}/checklist/{item_id}",
    response_model=ChecklistPatchResult,
    responses={
        401: {"description": "unauthorized: an Authorization header was sent but is invalid or expired"},
        403: {"description": "forbidden: not the owner (wrong user or missing/wrong X-Owner-Token)"},
        404: {"description": "not_found: unknown assessment, or the item is not part of it"},
    },
    summary="Tick or untick a checklist item (owner, or anonymous owner with X-Owner-Token)",
)
def update_checklist_item(
    assessment_id: int,
    item_id: int,
    body: ChecklistPatch,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
    x_owner_token: str | None = _OWNER_HEADER,
) -> ChecklistPatchResult:
    return assessment_service.update_checklist_item(db, assessment_id, item_id, body.done, user, x_owner_token)
