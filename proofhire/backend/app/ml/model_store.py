"""Artifact validation, loading and scoring (Member 1). Guidebook A12 + A6.

Runtime imports only stdlib, numpy, scikit-learn and joblib (guidebook D5 / A14: NO pandas, NO pydantic here, so
this module can be tested without the web stack). pipeline.py wraps it with the frozen public contract.

load_artifacts() runs the A12 startup checks in this order and raises ArtifactError (with the reason) on the first
failure - it never substitutes a fabricated model:
  1. model_meta.json exists, is JSON and has every required key; model_version matches proofhire-lr-MAJOR.MINOR.PATCH;
     thresholds satisfy 0 <= low < high <= 1
  2. sklearn_version in the meta equals the RUNNING scikit-learn (mismatch -> not loaded)
  3. feature_order in the meta equals features.FEATURE_ORDER (training/inference feature contract)
  4. model.joblib exists and its SHA-256 equals sha256_model (verified BEFORE joblib.load unpickles anything)
  5. joblib.load, then one warm-up prediction that must be a finite probability in [0, 1]
metrics.json is read when present (needed by /ml/metrics only); a missing/invalid file does not block scoring.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from app.ml import features

log = logging.getLogger("proofhire.ml")

ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
MODEL_FILENAME = "model.joblib"
META_FILENAME = "model_meta.json"
METRICS_FILENAME = "metrics.json"

REQUIRED_SKLEARN_VERSION = "1.7.2"  # guidebook Section 3.1 pin; tests/CI check the artifact against it
MAX_ARTIFACT_BYTES = 10 * 1024 * 1024  # guidebook A12 / A13: model.joblib under 10 MB

VERSION_RE = re.compile(r"^proofhire-lr-(\d+)\.(\d+)\.(\d+)$")
REQUIRED_META_KEYS = (
    "model_version", "trained_at", "sklearn_version", "python_version", "selected_model", "thresholds",
    "feature_order", "dataset", "sha256_model", "feedback_rows",
)
REQUIRED_DATASET_KEYS = ("type", "rows", "seed", "generator_commit")

# Fixed, fictional listing used only for the startup warm-up prediction (not a test of accuracy).
WARMUP_LISTING = {
    "title": "Warm-up Intern", "company_name": "Warmup Labs",
    "description": "Synthetic warm-up listing used only to exercise the loaded model once at startup.",
    "requirements": "", "work_mode": "onsite", "employment_type": "internship", "pay_period": "month",
    "application_channel": "email", "interview_mode": "video_call", "upfront_fee_amount": 0,
}


class ArtifactError(RuntimeError):
    """The artifact set is missing, inconsistent, tampered with or incompatible; the model was NOT loaded."""


@dataclass(frozen=True)
class LoadedArtifacts:
    pipeline: Any
    meta: dict
    metrics: Optional[dict]
    sha256: str


# ------------------------------------------------------------------ helpers
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def running_sklearn_version() -> str:
    import sklearn

    return sklearn.__version__


def parse_version(version: str) -> tuple[int, int, int]:
    m = VERSION_RE.match(version or "")
    if not m:
        raise ArtifactError(f"model_version {version!r} does not match proofhire-lr-MAJOR.MINOR.PATCH")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def format_version(major: int, minor: int, patch: int) -> str:
    return f"proofhire-lr-{major}.{minor}.{patch}"


def level_for(score: float, thresholds: dict) -> str:
    """A6: score >= high -> high; score < low -> low; otherwise medium."""
    if score >= thresholds["high"]:
        return "high"
    if score < thresholds["low"]:
        return "low"
    return "medium"


def validate_meta(meta: Any) -> None:
    """Structural checks on model_meta.json content (raises ArtifactError)."""
    if not isinstance(meta, dict):
        raise ArtifactError("model_meta.json is not a JSON object")
    missing = [k for k in REQUIRED_META_KEYS if k not in meta]
    if missing:
        raise ArtifactError(f"model_meta.json missing keys: {missing}")
    parse_version(meta["model_version"])
    th = meta["thresholds"]
    if not (isinstance(th, dict) and set(th) == {"low", "high"}):
        raise ArtifactError("model_meta.json thresholds must be {low, high}")
    low, high = th["low"], th["high"]
    if not (isinstance(low, (int, float)) and isinstance(high, (int, float)) and 0.0 <= low < high <= 1.0):
        raise ArtifactError(f"model_meta.json thresholds invalid: {th}")
    ds = meta["dataset"]
    if not isinstance(ds, dict) or any(k not in ds for k in REQUIRED_DATASET_KEYS):
        raise ArtifactError(f"model_meta.json dataset must contain {list(REQUIRED_DATASET_KEYS)}")
    if not (isinstance(meta["sha256_model"], str) and re.fullmatch(r"[0-9a-f]{64}", meta["sha256_model"])):
        raise ArtifactError("model_meta.json sha256_model is not a 64-char hex digest")


def _read_json(path: Path, what: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ArtifactError(f"{what} not found: {path}") from exc
    except (OSError, ValueError) as exc:
        raise ArtifactError(f"{what} unreadable ({exc.__class__.__name__}): {path}") from exc


def _model_matrix(listings: list):
    import numpy as np

    return np.array([features.model_input_values(item) for item in listings], dtype=object)


def predict_scores(pipeline: Any, listings: list) -> list[float]:
    """P(risky) for each listing, via the exact feature contract (features.model_input_values)."""
    proba = pipeline.predict_proba(_model_matrix(listings))
    return [float(p) for p in proba[:, 1]]


def predict_score(loaded: LoadedArtifacts, listing: Any) -> float:
    """Single-listing score rounded to 4 decimals (guidebook 5.3: float 0..1, 4 decimals)."""
    return round(predict_scores(loaded.pipeline, [listing])[0], 4)


# ------------------------------------------------------------------ the loader
def load_artifacts(directory: Optional[Path] = None) -> LoadedArtifacts:
    """Validate and load model.joblib + model_meta.json (+ metrics.json). See module docstring for the order."""
    d = Path(directory) if directory is not None else ARTIFACT_DIR
    meta = _read_json(d / META_FILENAME, META_FILENAME)
    validate_meta(meta)

    running = running_sklearn_version()
    if meta["sklearn_version"] != running:
        raise ArtifactError(
            f"scikit-learn mismatch: artifact trained with {meta['sklearn_version']}, running {running}. "
            f"Retrain and re-export with the pinned version ({REQUIRED_SKLEARN_VERSION})."
        )
    if running != REQUIRED_SKLEARN_VERSION:
        log.warning("scikit-learn %s is not the pinned %s; artifact matches the running version only",
                    running, REQUIRED_SKLEARN_VERSION)

    if list(meta["feature_order"]) != list(features.FEATURE_ORDER):
        raise ArtifactError("feature_order in model_meta.json differs from features.FEATURE_ORDER; retrain required")

    model_path = d / MODEL_FILENAME
    if not model_path.is_file():
        raise ArtifactError(f"{MODEL_FILENAME} not found: {model_path}")
    actual = sha256_file(model_path)
    if actual != meta["sha256_model"]:
        raise ArtifactError("model.joblib SHA-256 does not match model_meta.json sha256_model (corrupt or tampered)")

    try:
        import joblib

        pipeline = joblib.load(model_path)
    except Exception as exc:  # pickle/sklearn errors vary; any failure means "not loaded"
        raise ArtifactError(f"joblib.load failed ({exc.__class__.__name__}: {exc})") from exc

    try:
        score = predict_scores(pipeline, [WARMUP_LISTING])[0]
    except Exception as exc:
        raise ArtifactError(f"warm-up prediction failed ({exc.__class__.__name__}: {exc})") from exc
    if not (math.isfinite(score) and 0.0 <= score <= 1.0):
        raise ArtifactError(f"warm-up prediction is not a probability: {score!r}")

    metrics: Optional[dict] = None
    try:
        loaded_metrics = _read_json(d / METRICS_FILENAME, METRICS_FILENAME)
        metrics = loaded_metrics if isinstance(loaded_metrics, dict) else None
    except ArtifactError as exc:
        log.warning("%s", exc)

    return LoadedArtifacts(pipeline=pipeline, meta=meta, metrics=metrics, sha256=actual)
