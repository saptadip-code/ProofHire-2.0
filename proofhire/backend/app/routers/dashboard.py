"""GET /dashboard/summary, /dashboard/trends, /dashboard/model-metrics (guidebook Section 5.4 and B4).

All three are public (no login). Plain `def` routes run in a worker thread, so the database
queries never block the event loop.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.schemas.dashboard import DashboardSummary, TrendPoint
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get(
    "/summary",
    response_model=DashboardSummary,
    summary="Dashboard numbers from stored assessments (public)",
)
def summary(
    include_demo: bool = Query(False, description="true also counts seeded demo rows (is_synthetic_demo = 1)"),
    db: Session = Depends(get_db),
) -> DashboardSummary:
    return dashboard_service.get_summary(db, include_demo)


@router.get(
    "/trends",
    response_model=list[TrendPoint],
    summary="Assessments per day, zero-filled (public)",
)
def trends(
    days: int = Query(14, ge=1, le=60, description="number of days ending today (UTC), 1-60"),
    include_demo: bool = Query(False),
    db: Session = Depends(get_db),
) -> list[TrendPoint]:
    return dashboard_service.get_trends(db, days, include_demo)


@router.get(
    "/model-metrics",
    response_model=None,
    responses={
        200: {"description": "Contents of metrics.json plus model_version (same shape as GET /ml/metrics)"},
        503: {"description": "model_unavailable: metrics.json is missing or invalid (nothing is substituted)"},
    },
    summary="Model evaluation metrics from metrics.json (public)",
)
def model_metrics() -> JSONResponse:
    body = dashboard_service.load_model_metrics()  # raises 503 without any Cache-Control header
    return JSONResponse(content=body, headers={"Cache-Control": "public, max-age=300"})
