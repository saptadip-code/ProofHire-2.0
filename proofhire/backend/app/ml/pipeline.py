"""ML pipeline public contract (Member 1). Guidebook A2 / A12. Signatures below are FROZEN.

*** PHASE 3 (A-G3) ***
REAL: model loading + validation (sklearn version, feature order, SHA-256, warm-up), atomic reload, model_status(),
get_model_info(), get_metrics(), and the score / risk_level / thresholds / model_version of assess_listing().
STILL INTERIM (honestly empty, never fabricated): evidence (A-G4), checklist (A-G4), entities (A-G4: email only),
explanation (A-G5: fixed template text, source='template'), llm_meta (template). with_llm is accepted and ignored
until A-G5.

Honesty rules:
  * If no valid artifact is loaded, assess_listing()/predict_listing() raise ModelNotLoadedError (backend -> 503
    model_unavailable). There is no fallback score and no stub model.
  * load_model() never raises: failure is logged and model_status()['loaded'] is False.
  * reload_model() builds and validates the new artifact FIRST and only then swaps the reference; on any failure
    the previous model is kept and ModelNotLoadedError is raised.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Optional

from app.ml import model_store as store
from app.schemas.ml_schemas import (
    Entity,
    Explanation,
    ListingInput,
    LlmMeta,
    MlResult,
    Thresholds,
)

log = logging.getLogger("proofhire.ml")

IS_STUB = True  # evidence / checklist / explanation / entities are still interim until A-G4 / A-G5


class ModelNotLoadedError(RuntimeError):
    """Raised when no valid artifact is loaded (or a reload failed)."""


_LOCK = threading.Lock()
_STATE: Optional[store.LoadedArtifacts] = None
_LOAD_ERROR: Optional[str] = None
_ATTEMPTED = False


def _clear_caches() -> None:
    """Hook for reload_model(): the result cache and LLM cache (guidebook A12) arrive in A-G5/A-G6."""


def _try_load() -> None:
    """Load into the singleton; never raises. Failure leaves the model unloaded and records the reason."""
    global _STATE, _LOAD_ERROR, _ATTEMPTED
    try:
        loaded = store.load_artifacts()
    except store.ArtifactError as exc:
        with _LOCK:
            _STATE, _LOAD_ERROR, _ATTEMPTED = None, str(exc), True
        log.error("ML model NOT loaded: %s", exc)
        return
    with _LOCK:
        _STATE, _LOAD_ERROR, _ATTEMPTED = loaded, None, True
    log.info("ML model loaded: %s (sklearn %s)", loaded.meta["model_version"], loaded.meta["sklearn_version"])


def _require_state() -> store.LoadedArtifacts:
    if not _ATTEMPTED:  # first use without a lifespan hook (scripts, tests): try exactly once
        _try_load()
    state = _STATE
    if state is None:
        raise ModelNotLoadedError(_LOAD_ERROR or "Model artifact not loaded")
    return state


def _score_and_level(listing: ListingInput) -> tuple[store.LoadedArtifacts, float, str]:
    state = _require_state()
    score = store.predict_score(state, listing)
    return state, score, store.level_for(score, state.meta["thresholds"])


def predict_listing(listing: ListingInput) -> dict:
    """Score only (POST /ml/predict): no evidence, no LLM, no DB. Returns {risk_score, risk_level, thresholds,
    model_version}. NOTE: not named in guidebook A2 (added so /predict does not run the rest of the pipeline)."""
    state, score, level = _score_and_level(listing)
    return {"risk_score": score, "risk_level": level,
            "thresholds": dict(state.meta["thresholds"]), "model_version": state.meta["model_version"]}


def interim_entities(listing: ListingInput) -> list[Entity]:
    """INTERIM (A-G4 replaces it with entities.extract_entities): the normalised contact email only."""
    return [Entity(type="email", value=listing.contact_email.strip().lower())] if listing.contact_email else []


def assess_listing(listing: ListingInput, with_llm: bool = True) -> MlResult:
    """Pure function: no DB, no auth. Real score/level/thresholds/model_version; interim evidence, checklist and
    explanation until A-G4/A-G5. Never raises for LLM failures; raises ModelNotLoadedError without a valid model."""
    state, score, level = _score_and_level(listing)
    explanation = Explanation(
        source="template",
        summary=("[A-G3 interim] The risk score and level come from the trained model. Evidence, checklist and "
                 "written explanation are not implemented yet (phases A-G4/A-G5)."),
        key_concerns=[],
        what_to_verify=[],
    )
    return MlResult(
        risk_score=score,
        risk_level=level,
        thresholds=Thresholds(**state.meta["thresholds"]),
        model_version=state.meta["model_version"],
        evidence=[],
        explanation=explanation,
        checklist=[],
        entities=interim_entities(listing),
        llm_meta=LlmMeta(provider="template", model="template", latency_ms=0, success=True, error_code=None),
    )


def load_model() -> None:
    """Called once from FastAPI lifespan startup. Never raises; on failure model_status()['loaded'] is False."""
    _try_load()


def reload_model() -> dict:
    """Re-read artifacts, validate, swap atomically. Returns the new model_meta dict. On failure the old model is
    kept and ModelNotLoadedError is raised."""
    global _STATE, _LOAD_ERROR, _ATTEMPTED
    try:
        loaded = store.load_artifacts()  # build + validate the new object first
    except store.ArtifactError as exc:
        log.error("ML reload failed, previous model kept: %s", exc)
        raise ModelNotLoadedError(str(exc)) from exc
    with _LOCK:
        _STATE, _LOAD_ERROR, _ATTEMPTED = loaded, None, True
    _clear_caches()
    log.info("ML model reloaded: %s", loaded.meta["model_version"])
    return dict(loaded.meta)


def _llm_enabled() -> bool:
    return os.environ.get("LLM_ENABLED", "false").strip().lower() == "true"


def model_status() -> dict:
    """{loaded, model_version, trained_at, sklearn_version (RUNNING version), llm_enabled}."""
    if not _ATTEMPTED:
        _try_load()
    state = _STATE
    try:
        running: Optional[str] = store.running_sklearn_version()
    except ImportError:
        running = None
    return {
        "loaded": state is not None,
        "model_version": state.meta["model_version"] if state else None,
        "trained_at": state.meta["trained_at"] if state else None,
        "sklearn_version": running,
        "llm_enabled": _llm_enabled(),
    }


def llm_circuit_open() -> bool:
    """STUB. The real circuit breaker lands in A-G5."""
    return False


def get_model_info() -> Optional[dict]:
    """model_meta.json contents of the LOADED model; None while no valid artifact is loaded."""
    if not _ATTEMPTED:
        _try_load()
    return dict(_STATE.meta) if _STATE else None


def get_metrics() -> Optional[dict]:
    """metrics.json contents of the loaded artifact set; None if not loaded or metrics.json missing.
    NOTE: guidebook Part B references get_metrics() but A2 does not define it."""
    if not _ATTEMPTED:
        _try_load()
    return dict(_STATE.metrics) if _STATE and _STATE.metrics is not None else None


def get_load_error() -> Optional[str]:
    """Why the model is not loaded (None when loaded). Diagnostics only; NOT part of the guidebook contract."""
    return _LOAD_ERROR


def _reset_for_tests() -> None:
    """Forget the singleton so tests can exercise load/reload paths. Not for production use."""
    global _STATE, _LOAD_ERROR, _ATTEMPTED
    with _LOCK:
        _STATE, _LOAD_ERROR, _ATTEMPTED = None, None, False
