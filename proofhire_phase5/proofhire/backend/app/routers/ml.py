"""ML HTTP endpoints (Member 1). Guidebook A11. Mounted by main.py as
    app.include_router(ml.router, prefix='/api/v1/ml')

PHASE 4 (A-G4): /predict is the real model score only (no evidence, no LLM, no DB). /evidence returns the real
observed + model evidence (E1..En); /explain returns the full MlResult (evidence, checklist, entities, template
explanation until A-G5 adds the LLM); /extract-entities returns the normalised A9 entities and needs no model.
Without a valid loaded model predict / evidence / explain return 503 model_unavailable; model-info and metrics
return 503 as well; reload returns 500 and keeps the old model. model-info and metrics send
Cache-Control: public, max-age=300 and an ETag (If-None-Match -> 304). The X-ProofHire-Stub header of earlier
phases is only sent while pipeline.IS_STUB is True (now False).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Optional

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse, Response

from app.ml import entities, pipeline
from app.schemas.ml_schemas import (
    EvidenceResponse,
    ExtractEntitiesResponse,
    ListingInput,
    MlHealthResponse,
    MlResult,
    PredictResponse,
    ReloadResponse,
)

router = APIRouter()


class MlHttpError(Exception):
    """Carries a Section 5.5 error body. Handled by the dependency/route wrappers."""

    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "fields": []}},
    )


def verify_internal_key(x_internal_key: Optional[str] = Header(default=None)) -> None:
    """X-Internal-Key must equal env INTERNAL_API_KEY; skipped when env var is empty."""
    expected = os.environ.get("INTERNAL_API_KEY", "")
    if not expected:
        return
    if x_internal_key is None or not hmac.compare_digest(x_internal_key, expected):
        raise MlHttpError(401, "unauthorized", "Invalid or missing X-Internal-Key")


def _stub_headers(response_headers) -> None:
    if pipeline.IS_STUB:
        response_headers["X-ProofHire-Stub"] = "true"


def _cached_json(request: Request, content: dict, etag_source: str) -> Response:
    """JSON 200 with Cache-Control public/max-age=300 and a strong ETag; 304 when If-None-Match matches."""
    etag = f'"{etag_source}"'
    headers = {"Cache-Control": "public, max-age=300", "ETag": etag}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return JSONResponse(content=content, headers=headers)


def _model_unavailable(exc: Exception) -> JSONResponse:
    return _error(503, "model_unavailable", "Model artifact not loaded")


def _auth(x_internal_key: Optional[str]) -> Optional[JSONResponse]:
    try:
        verify_internal_key(x_internal_key)
    except MlHttpError as e:
        return _error(e.status, e.code, e.message)
    return None


@router.get("/health", response_model=MlHealthResponse)
def ml_health() -> MlHealthResponse:
    s = pipeline.model_status()
    return MlHealthResponse(
        loaded=s["loaded"],
        model_version=s["model_version"],
        trained_at=s["trained_at"],
        sklearn_version=s["sklearn_version"],
        llm_enabled=s["llm_enabled"],
        llm_circuit_open=pipeline.llm_circuit_open(),
    )


@router.get("/model-info")
def ml_model_info(request: Request):
    info = pipeline.get_model_info()
    if info is None:
        return _error(503, "model_unavailable", "Model artifact not loaded")
    return _cached_json(request, info, info["sha256_model"])  # ETag = model sha256 (A11)


@router.get("/metrics")
def ml_metrics(request: Request):
    m = pipeline.get_metrics()
    if m is None:
        return _error(503, "model_unavailable", "Model metrics not available")
    digest = hashlib.sha256(json.dumps(m, sort_keys=True).encode("utf-8")).hexdigest()
    return _cached_json(request, m, digest)


@router.post("/predict", response_model=PredictResponse)
def ml_predict(listing: ListingInput, x_internal_key: Optional[str] = Header(default=None)):
    if (err := _auth(x_internal_key)) is not None:
        return err
    try:
        scored = pipeline.predict_listing(listing)  # score only: no evidence, no LLM, no DB
    except pipeline.ModelNotLoadedError as exc:
        return _model_unavailable(exc)
    body = PredictResponse(**scored)
    return JSONResponse(content=body.model_dump(mode="json"))


@router.post("/evidence", response_model=EvidenceResponse)
def ml_evidence(listing: ListingInput, x_internal_key: Optional[str] = Header(default=None)):
    if (err := _auth(x_internal_key)) is not None:
        return err
    try:
        r = pipeline.assess_listing(listing, with_llm=False)
    except pipeline.ModelNotLoadedError as exc:
        return _model_unavailable(exc)
    body = EvidenceResponse(risk_score=r.risk_score, risk_level=r.risk_level, evidence=r.evidence)
    resp = JSONResponse(content=body.model_dump(mode="json"))
    _stub_headers(resp.headers)
    return resp


@router.post("/explain", response_model=MlResult)
def ml_explain(listing: ListingInput, x_internal_key: Optional[str] = Header(default=None)):
    if (err := _auth(x_internal_key)) is not None:
        return err
    try:
        r = pipeline.assess_listing(listing, with_llm=True)
    except pipeline.ModelNotLoadedError as exc:
        return _model_unavailable(exc)
    resp = JSONResponse(content=r.model_dump(mode="json"))
    _stub_headers(resp.headers)
    return resp


@router.post("/extract-entities", response_model=ExtractEntitiesResponse)
def ml_extract_entities(listing: ListingInput, x_internal_key: Optional[str] = Header(default=None)):
    if (err := _auth(x_internal_key)) is not None:
        return err
    body = ExtractEntitiesResponse(entities=entities.extract_entities(listing))  # A9; needs no model
    resp = JSONResponse(content=body.model_dump(mode="json"))
    _stub_headers(resp.headers)
    return resp


@router.post("/reload", response_model=ReloadResponse)
def ml_reload(x_internal_key: Optional[str] = Header(default=None)):
    if (err := _auth(x_internal_key)) is not None:
        return err
    try:
        meta = pipeline.reload_model()
    except Exception:
        return _error(500, "internal_error", "Model artifact invalid or missing; previous model kept")
    return ReloadResponse(reloaded=True, model_version=meta["model_version"], sha256=meta["sha256_model"])
