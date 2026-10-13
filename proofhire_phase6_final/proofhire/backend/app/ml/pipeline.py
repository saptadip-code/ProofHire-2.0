"""ML pipeline public contract (Member 1). Guidebook A2 / A12. Signatures below are FROZEN.

*** PHASE 5 (A-G5) ***
REAL: model loading + validation (sklearn version, feature order, SHA-256, warm-up), atomic reload, model_status(),
get_model_info(), get_metrics(); and in assess_listing(): the score / risk_level / thresholds / model_version, the
observed + model-derived evidence (evidence.py, ids E1..En), the checklist (checklist.py, content owned by Member 4),
the normalised entities (entities.py, A9) and a deterministic template explanation (template_explainer.py) whose
concerns reference only ids present in the evidence list. The 100-entry / 10-minute result cache (A12) lives here.
A-G5: the explanation comes from llm_client.generate_explanation() when `with_llm` is True AND LLM_ENABLED=true:
an LLM explanation (llm_meta.provider 'groq' / 'openrouter') or, on any problem, the deterministic template
(llm_meta.provider 'template', success False + error_code). `with_llm=False` / LLM disabled -> template, no network.
llm_circuit_open() reports the real circuit breaker. The LLM can never reach the score: it is called after the score,
level and evidence are fixed and only returns an Explanation + LlmMeta.

Honesty rules:
  * If no valid artifact is loaded, assess_listing()/predict_listing() raise ModelNotLoadedError (backend -> 503
    model_unavailable). There is no fallback score and no stub model.
  * load_model() never raises: failure is logged and model_status()['loaded'] is False.
  * reload_model() builds and validates the new artifact FIRST and only then swaps the reference; on any failure
    the previous model is kept and ModelNotLoadedError is raised. A successful reload clears the result cache.
  * The score and level are decided BEFORE evidence / checklist / explanation are built and nothing downstream can
    change them (the explanation builders only receive the level, the evidence and the checklist hint texts).
  * A template fallback produced because the LLM was wanted but failed is NEVER stored in the result cache (so the
    next identical request retries the LLM); an LLM explanation and a deliberate template (LLM off) are cached.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict
from typing import Callable, Optional

from app.ml import checklist as checklist_mod
from app.ml import entities as entities_mod
from app.ml import evidence as evidence_mod
from app.ml import features
from app.ml import llm_client
from app.ml import model_store as store
from app.ml import template_explainer
from app.schemas.ml_schemas import (
    ListingInput,
    LlmMeta,
    MlResult,
    Thresholds,
)

log = logging.getLogger("proofhire.ml")

IS_STUB = False  # A-G5: model, evidence, checklist, entities and the LLM/template explanation are all real


class ModelNotLoadedError(RuntimeError):
    """Raised when no valid artifact is loaded (or a reload failed)."""


_LOCK = threading.Lock()  # guards the singleton reference (swap is a single assignment under this lock)
_RELOAD_LOCK = threading.Lock()  # serialises reloads so two validations never race to swap
_STATE: Optional[store.LoadedArtifacts] = None
_LOAD_ERROR: Optional[str] = None
_ATTEMPTED = False


RESULT_CACHE_MAX_ENTRIES = 100  # guidebook A12
RESULT_CACHE_TTL_SECONDS = 600.0  # 10 minutes


class _ResultCache:
    """Thread-safe LRU + TTL cache of finished MlResult objects (stores and returns deep copies).

    Only listing-derived data is ever cached: the key is built from ListingInput alone (no user id, JWT, owner token
    or any other per-user field reaches this module), plus the model identity and the effective explanation mode.
    """

    def __init__(self, max_entries: int, ttl_seconds: float, clock: Callable[[], float] = time.monotonic):
        self._max, self._ttl, self._clock = max_entries, ttl_seconds, clock
        self._data: "OrderedDict[str, tuple[float, MlResult]]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[MlResult]:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            if self._clock() - entry[0] >= self._ttl:
                del self._data[key]
                return None
            self._data.move_to_end(key)
            return entry[1].model_copy(deep=True)

    def put(self, key: str, result: MlResult) -> None:
        with self._lock:
            self._data[key] = (self._clock(), result.model_copy(deep=True))
            self._data.move_to_end(key)
            while len(self._data) > self._max:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)


_RESULT_CACHE = _ResultCache(RESULT_CACHE_MAX_ENTRIES, RESULT_CACHE_TTL_SECONDS)


def _result_cache_key(listing: ListingInput, state: store.LoadedArtifacts, use_llm: bool) -> str:
    """SHA-256 of the normalised listing JSON (+ model identity + effective LLM mode).

    `use_llm` is the EFFECTIVE mode (with_llm requested AND LLM enabled), so a with_llm=False (evidence-only) result
    can never be served to a with_llm=True caller, or the other way round, now that the explanations differ.
    """
    payload = {
        "listing": listing.model_dump(mode="json"),
        "model_version": state.meta["model_version"],
        "model_sha256": state.sha256,
        "thresholds": state.meta["thresholds"],
        "llm": bool(use_llm),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def _clear_caches() -> None:
    """Hook for reload_model(): drop cached results (they embed the old model), the LLM cache (A11/A12) and re-read
    the checklist library. The circuit breaker and rate limiter are NOT reset (they describe the provider, not the model)."""
    _RESULT_CACHE.clear()
    llm_client.clear_cache()
    checklist_mod.clear_cache()


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


def assess_listing(listing: ListingInput, with_llm: bool = True) -> MlResult:
    """Pure function: no DB, no auth. Real score / level / thresholds / model_version, observed + model evidence
    (E1..En), checklist, entities, LLM or template explanation. Never raises for explanation / LLM problems; raises
    ModelNotLoadedError only when no valid model is loaded.

    Order matters: the score and level are fixed first; evidence, checklist, entities and the explanation are
    derived afterwards and cannot alter them.
    """
    state = _require_state()
    use_llm = bool(with_llm) and _llm_enabled()
    key = _result_cache_key(listing, state, use_llm)
    cached = _RESULT_CACHE.get(key)
    if cached is not None:
        if cached.llm_meta.provider != "template":
            cached.llm_meta.latency_ms = 0  # served from the result cache: no LLM call was made for this response
        return cached

    feats = features.build_row(listing)
    score = store.predict_score(state, listing)
    level = store.level_for(score, state.meta["thresholds"])

    evidence = evidence_mod.build_evidence(listing, feats, state.pipeline)
    checklist = checklist_mod.build_checklist(evidence)
    entities = entities_mod.extract_entities(listing)
    hints = [c.text for c in checklist]
    if use_llm:
        explanation, llm_meta = llm_client.generate_explanation(level, list(evidence), hints)  # never raises
    else:
        explanation = template_explainer.build_template_explanation(level, list(evidence), hints)  # copies: cannot alter evidence
        llm_meta = LlmMeta(provider="template", model="template", latency_ms=0, success=True, error_code=None)

    result = MlResult(
        risk_score=score,
        risk_level=level,
        thresholds=Thresholds(**state.meta["thresholds"]),
        model_version=state.meta["model_version"],
        evidence=evidence,
        explanation=explanation,
        checklist=checklist,
        entities=entities,
        llm_meta=llm_meta,
    )
    if not use_llm or explanation.source.value == "llm":  # never cache "LLM wanted but failed" under the LLM key
        _RESULT_CACHE.put(key, result)
    return result


def load_model() -> None:
    """Called once from FastAPI lifespan startup. Never raises; on failure model_status()['loaded'] is False.
    Idempotent: when a model is already loaded it does nothing (use reload_model() to swap in a new artifact), so a
    second call can never drop a working model."""
    if _STATE is not None:
        return
    _try_load()


def reload_model() -> dict:
    """Re-read artifacts, validate, swap atomically. Returns the new model_meta dict. On failure the old model is
    kept and ModelNotLoadedError is raised."""
    global _STATE, _LOAD_ERROR, _ATTEMPTED
    with _RELOAD_LOCK:
        try:
            loaded = store.load_artifacts()  # build + validate the new object first (sklearn, meta, SHA-256, warm-up)
        except store.ArtifactError as exc:
            log.error("ML reload failed, previous model kept: %s", exc)
            raise ModelNotLoadedError(str(exc)) from exc
        with _LOCK:  # atomic swap: readers see the old or the new model, never a mix
            _STATE, _LOAD_ERROR, _ATTEMPTED = loaded, None, True
        _clear_caches()
    log.info("ML model reloaded: %s", loaded.meta["model_version"])
    return dict(loaded.meta)


def _llm_enabled() -> bool:
    return llm_client.llm_enabled()  # LLM_ENABLED=true (default false: tests and keyless setups use the template)


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
    """True while the LLM circuit breaker is open (3 consecutive failures -> skip the LLM for 120 s)."""
    return llm_client.circuit_open()


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
    _RESULT_CACHE.clear()
