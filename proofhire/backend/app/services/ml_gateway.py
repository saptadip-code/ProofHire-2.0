"""The ONLY place the backend touches Member 1's ML package (guidebook C2, A2, B4).

Agreed interface (guidebook A2):

    app.schemas.ml_schemas.ListingInput                 Member 1's request model
    app.ml.pipeline.assess_listing(listing, with_llm=True) -> MlResult
    app.ml.pipeline.model_status() -> {loaded, model_version, ...}

STATUS: INTEGRATED. The real ML package (app.ml, app.schemas.ml_schemas) is now part of
the project. If it is ever missing or the model is not loaded, every call here ends in
503 model_unavailable. Nothing in this file scores a listing. It does not guess results
and has no fallback engine.

What it does:
  1. imports the two ML modules lazily (a missing module = 503, the app still starts)
  2. refuses to call the pipeline if model_status() says the model is not loaded (503)
  3. converts the validated request to Member 1's ListingInput and calls assess_listing
  4. checks the answer against the documented Section 5.3 / A2 shape (MlOutput below)
     and returns it. A wrong shape is an integration bug: logged, answered with 500.

MlOutput is the backend's read-only view of what A2 says assess_listing returns.
It is NOT a replacement for Member 1's MlResult and ignores extra fields, so
Member 1 can add fields without breaking the backend. When the real files arrive,
compare the two and record any difference in docs/CONTRACT_CHANGELOG.md.
"""

from __future__ import annotations

import importlib
import logging
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.core.errors import AppError, model_unavailable
from app.schemas.assessment import ListingInput

logger = logging.getLogger("proofhire.ml_gateway")


# ---- the documented shape of Member 1's result (Section 5.3 without DB fields + llm_meta) ----
class MlThresholds(BaseModel):
    low: float = Field(ge=0, le=1)
    high: float = Field(ge=0, le=1)


class MlEvidence(BaseModel):
    id: str = Field(min_length=1, max_length=8)  # E1, E2 ...
    code: str = Field(min_length=1, max_length=64)
    label: str
    type: Literal["observed", "model"]
    direction: Literal["increases_risk", "decreases_risk"]
    severity: int = Field(ge=1, le=3)
    snippet: str | None = None
    weight: float | None = None


class MlKeyConcern(BaseModel):
    text: str
    evidence_ids: list[str] = Field(default_factory=list)


class MlExplanation(BaseModel):
    source: Literal["llm", "template"]
    summary: str
    key_concerns: list[MlKeyConcern] = Field(default_factory=list)
    what_to_verify: list[str] = Field(default_factory=list)


class MlChecklistItem(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    text: str
    priority: int = Field(ge=1, le=255)


class MlEntity(BaseModel):
    type: Literal["email", "email_domain", "phone", "website_domain", "company_name"]
    value: str


class MlLlmMeta(BaseModel):
    provider: str
    model: str
    latency_ms: int = Field(ge=0)
    success: bool
    error_code: str | None = None


class MlOutput(BaseModel):
    risk_score: float = Field(ge=0, le=1)
    risk_level: Literal["low", "medium", "high"]
    thresholds: MlThresholds
    model_version: str = Field(min_length=1, max_length=64)
    evidence: list[MlEvidence] = Field(default_factory=list)
    explanation: MlExplanation
    checklist: list[MlChecklistItem] = Field(default_factory=list)
    entities: list[MlEntity] = Field(default_factory=list)
    llm_meta: MlLlmMeta | None = None


# ---- the call ----------------------------------------------------------------------
def _import_ml():
    """Return (pipeline module, ml_schemas module) or raise 503 if either is missing."""
    try:
        pipeline = importlib.import_module("app.ml.pipeline")
        ml_schemas = importlib.import_module("app.schemas.ml_schemas")
    except ImportError as exc:
        logger.warning("ML integration pending: cannot import %s", getattr(exc, "name", None) or "ML module")
        raise model_unavailable() from None
    except Exception as exc:  # noqa: BLE001 - broken ML code must not crash the request handler
        logger.error("Importing the ML package failed: %s", type(exc).__name__)
        raise model_unavailable() from None
    return pipeline, ml_schemas


def run_assessment(listing: ListingInput) -> MlOutput:
    """Score one listing through Member 1's pipeline. Raises AppError (503 or 500) on failure."""
    pipeline, ml_schemas = _import_ml()

    assess = getattr(pipeline, "assess_listing", None)
    ml_listing_cls = getattr(ml_schemas, "ListingInput", None)
    if not callable(assess) or ml_listing_cls is None:
        logger.error("ML integration incomplete: assess_listing or ml_schemas.ListingInput is missing")
        raise model_unavailable()

    # B4 step 3: model not loaded -> 503 model_unavailable.
    status_fn = getattr(pipeline, "model_status", None)
    if callable(status_fn):
        try:
            status = status_fn()
        except Exception as exc:  # noqa: BLE001
            logger.error("model_status() failed: %s", type(exc).__name__)
            raise model_unavailable() from None
        if isinstance(status, dict) and not status.get("loaded"):
            raise model_unavailable()

    try:
        ml_listing = ml_listing_cls.model_validate(listing.model_dump())
        raw = assess(ml_listing, with_llm=True)
    except AppError:
        raise
    except Exception as exc:
        if isinstance(exc, getattr(pipeline, "ModelNotLoadedError", ())):
            logger.warning("ML model unavailable during assessment")
            raise model_unavailable() from None
        # Class name only: exception text could contain the submitted listing.
        logger.error("assess_listing failed: %s", type(exc).__name__)
        raise AppError("internal_error", "The assessment engine failed", 500) from None

    data = raw.model_dump() if hasattr(raw, "model_dump") else raw
    try:
        return MlOutput.model_validate(data)
    except ValidationError as exc:
        # Field paths only (no values) so the log shows what differs from the contract.
        problems = sorted({".".join(str(p) for p in e["loc"]) for e in exc.errors()})[:10]
        logger.error("assess_listing returned an unexpected shape; problem fields: %s", problems)
        raise AppError("internal_error", "The assessment engine returned an unexpected result", 500) from None
