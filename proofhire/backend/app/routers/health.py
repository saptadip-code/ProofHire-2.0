"""GET /api/v1/health: liveness and readiness probe (guidebook B4).

Public, never cached, and always answers 200 even when degraded, so the
frontend wake-up banner and Render's health check can read the details.
It never raises: a down database or a missing model is reported, not crashed on.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Response

from app.core.config import APP_VERSION
from app.db.session import check_db
from app.schemas.health import HealthResponse

logger = logging.getLogger("proofhire.health")
router = APIRouter(tags=["health"])

_warned_ml_unavailable = False


def _ml_status() -> dict:
    """Ask Member 1's pipeline for model_status(); {} if it is missing or fails.

    The ML package is owned by Member 1 (changes C2). This only calls their
    documented model_status() and falls back to "not loaded" on any problem,
    matching B3 (a failed model load must not stop the app).
    """
    global _warned_ml_unavailable
    try:
        from app.ml.pipeline import model_status  # Member 1's public interface

        status = model_status()
        return status if isinstance(status, dict) else {}
    except Exception as exc:  # noqa: BLE001 - health must never raise
        if not _warned_ml_unavailable:  # log once, not on every probe
            logger.warning("ML model status unavailable: %s", type(exc).__name__)
            _warned_ml_unavailable = True
        return {}


def build_health() -> HealthResponse:
    db_ok, db_error = check_db()
    if not db_ok:
        logger.warning("Health check: database unavailable (%s)", db_error)

    ml = _ml_status()
    model_loaded = bool(ml.get("loaded"))
    version = ml.get("model_version")

    return HealthResponse(
        status="ok" if (db_ok and model_loaded) else "degraded",
        db=db_ok,
        model_loaded=model_loaded,
        model_version=version if model_loaded and isinstance(version, str) else None,
        llm_enabled=bool(ml.get("llm_enabled")),
        version=APP_VERSION,
    )


@router.get("/health", response_model=HealthResponse, summary="Liveness and readiness probe")
def health(response: Response) -> HealthResponse:
    # Plain `def`: FastAPI runs it in a worker thread, so the blocking
    # SELECT 1 does not stall the event loop.
    response.headers["Cache-Control"] = "no-store"  # B4: no caching
    return build_health()
