"""Response model for GET /api/v1/health (guidebook B4)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    # "ok" only when the database answers AND the ML model is loaded
    # (Section 13: a healthy deploy shows status ok, db true, model_loaded true).
    status: Literal["ok", "degraded"]
    db: bool
    model_loaded: bool
    model_version: str | None
    llm_enabled: bool
    version: str
