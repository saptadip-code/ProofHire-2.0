"""Shared offline modelling helpers for train.py / evaluate.py / export_artifacts.py (Member 1). Guidebook A5, A6.

Offline only (NOT deployed): may import pandas. Nothing here is imported by the runtime service.

Feature contract: every model consumes ONE input matrix whose columns are features.MODEL_INPUT_COLUMNS
([text] + FEATURE_ORDER), built by features.model_input_values() - the same function inference uses. The
ColumnTransformers select columns by position in that list (so no pandas is needed at inference); the
transformer names (tfidf / num / bin / cat) and every hyper-parameter are the guidebook A5 values.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

import numpy as np

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
if str(REPO_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "backend"))

from sklearn.compose import ColumnTransformer  # noqa: E402
from sklearn.dummy import DummyClassifier  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier  # noqa: E402
from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    accuracy_score, average_precision_score, brier_score_loss, confusion_matrix, f1_score,
    precision_recall_curve, precision_score, recall_score, roc_auc_score,
)
from sklearn.pipeline import Pipeline  # noqa: E402
from sklearn.preprocessing import OneHotEncoder, StandardScaler  # noqa: E402

from app.ml import features as F  # noqa: E402

SEED = 42
DEFAULT_CSV = HERE / "data" / "listings_synthetic.csv"
DATA_README = HERE / "data" / "README.md"
BUILD_DIR = HERE / "build"
REPORTS_DIR = HERE / "reports"
HANDWRITTEN_CSV = REPO_ROOT / "demo_data" / "handwritten_eval.csv"
ARTIFACT_DIR = REPO_ROOT / "backend" / "app" / "ml" / "artifacts"

DECISION_THRESHOLD = 0.5  # fixed cut-off for precision / recall / F1 / accuracy / confusion (guidebook gives none)
CHALLENGER_MARGIN = 0.02  # A5 step 6: M4 must beat M3 val PR-AUC by MORE than this
PRECISION_TARGET, RECALL_TARGET = 0.90, 0.95  # A6
MIN_THRESHOLD_GAP = 0.15  # A6
FALLBACK_THRESHOLDS = {"low": 0.35, "high": 0.70}  # A6
HOLDOUT_PATTERN = "fake_offer_letter"

MODEL_NAMES = {
    "M0": ("DummyClassifier (stratified)", "none (floor baseline)"),
    "M1": ("LogisticRegression", "TF-IDF text only"),
    "M2": ("RandomForestClassifier", "structured features only"),
    "M3": ("LogisticRegression", "TF-IDF + scaled numeric + binary + one-hot categorical (PRODUCTION)"),
    "M4": ("HistGradientBoostingClassifier", "structured features only (challenger)"),
}

_COL_IDX = {c: i for i, c in enumerate(F.MODEL_INPUT_COLUMNS)}
TEXT_IDX = _COL_IDX[F.TEXT_COL]
NUM_IDX = [_COL_IDX[c] for c in F.NUM_COLS]
BIN_IDX = [_COL_IDX[c] for c in F.BIN_COLS]
CAT_IDX = [_COL_IDX[c] for c in F.CAT_COLS]


# ------------------------------------------------------------------ data
def load_dataset(csv_path: Path = DEFAULT_CSV):
    """Read the synthetic CSV as strings (blanks stay ''), per guidebook A3 (no cleaning step)."""
    import pandas as pd

    # utf-8-sig: also accepts Excel's "CSV UTF-8" (BOM) without mangling the first column name. Excel's plain "CSV
    # (Comma delimited)" on Windows writes cp1252 (curly quotes, en dashes): fall back to it instead of crashing.
    try:
        return pd.read_csv(csv_path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except UnicodeDecodeError:
        return pd.read_csv(csv_path, dtype=str, keep_default_na=False, encoding="cp1252")


def build_matrix(df) -> tuple[np.ndarray, np.ndarray]:
    """(X, y): X is the object matrix aligned with MODEL_INPUT_COLUMNS, y the int label (TARGET)."""
    X = np.array([F.model_input_values(rec) for rec in df.to_dict("records")], dtype=object)
    y = df["label"].astype(int).to_numpy()
    return X, y


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_dataset_provenance(readme: Path = DATA_README) -> dict:
    """seed / generator commit / csv sha256 recorded by generate_synthetic.py in ml/data/README.md."""
    out: dict[str, Any] = {"seed": None, "generator_commit": None, "csv_sha256": None}
    try:
        text = readme.read_text(encoding="utf-8")
    except OSError:
        return out
    if m := re.search(r"Seed:\s*\*\*(\d+)\*\*", text):
        out["seed"] = int(m.group(1))
    if m := re.search(r"Generator commit hash[^`]*`([^`]+)`", text):
        commit = m.group(1).strip()
        out["generator_commit"] = None if commit.lower().startswith("unknown") else commit
    if m := re.search(r"CSV sha256:\s*`([0-9a-f]{64})`", text):
        out["csv_sha256"] = m.group(1)
    return out


def git_commit_or_none() -> Optional[str]:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None
    except (OSError, subprocess.SubprocessError):
        return None


# ------------------------------------------------------------------ models (A5)
def _tfidf() -> TfidfVectorizer:
    return TfidfVectorizer(ngram_range=(1, 2), min_df=3, max_features=3000, sublinear_tf=True, strip_accents="unicode")


def _structured_prep() -> ColumnTransformer:
    return ColumnTransformer([
        ("num", "passthrough", NUM_IDX),
        ("bin", "passthrough", BIN_IDX),
        ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CAT_IDX),
    ])


def make_model(model_id: str):
    """Unfitted model for M0..M4 with the exact guidebook A5 hyper-parameters."""
    if model_id == "M0":
        return DummyClassifier(strategy="stratified", random_state=SEED)
    if model_id == "M1":
        prep = ColumnTransformer([("tfidf", _tfidf(), TEXT_IDX)])
        clf = LogisticRegression(C=1.0, solver="liblinear", max_iter=500)
        return Pipeline([("prep", prep), ("clf", clf)])
    if model_id == "M2":
        clf = RandomForestClassifier(n_estimators=200, max_depth=12, min_samples_leaf=3, n_jobs=1, random_state=SEED)
        return Pipeline([("prep", _structured_prep()), ("clf", clf)])
    if model_id == "M3":  # PRODUCTION. No class_weight, so probabilities stay roughly calibrated.
        prep = ColumnTransformer([
            ("tfidf", _tfidf(), TEXT_IDX),
            ("num", StandardScaler(), NUM_IDX),
            ("bin", "passthrough", BIN_IDX),
            ("cat", OneHotEncoder(handle_unknown="ignore"), CAT_IDX),
        ])
        clf = LogisticRegression(C=1.0, solver="liblinear", max_iter=500, random_state=SEED)
        return Pipeline([("prep", prep), ("clf", clf)])
    if model_id == "M4":
        clf = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.08, max_depth=6, random_state=SEED)
        return Pipeline([("prep", _structured_prep()), ("clf", clf)])
    raise ValueError(f"unknown model id {model_id!r}")


def fit_model(model, X, y, sample_weight=None):
    """Fit M0..M4; `sample_weight` (used by retrain.py for feedback rows) is routed to the final classifier."""
    if sample_weight is None:
        return model.fit(X, y)
    if isinstance(model, Pipeline):
        return model.fit(X, y, clf__sample_weight=np.asarray(sample_weight, dtype=float))
    return model.fit(X, y, sample_weight=np.asarray(sample_weight, dtype=float))


def positive_scores(model, X) -> np.ndarray:
    return model.predict_proba(X)[:, 1]


def select_model(m3_val_pr_auc: float, m4_val_pr_auc: float, accept_challenger: bool = False) -> tuple[str, str]:
    """A5 step 6. VALIDATION numbers only (never test). M3 unless M4's val PR-AUC beats it by MORE than 0.02
    AND the team has agreed to give up coefficient-based evidence (accept_challenger)."""
    gap = m4_val_pr_auc - m3_val_pr_auc
    if gap > CHALLENGER_MARGIN:
        if accept_challenger:
            return "M4", f"M4 val PR-AUC beats M3 by {gap:.4f} (> {CHALLENGER_MARGIN}) and the team accepted it"
        return "M3", (f"M4 val PR-AUC beats M3 by {gap:.4f} (> {CHALLENGER_MARGIN}) but the team has NOT accepted "
                      "losing coefficient-based evidence (pass --accept-challenger to switch)")
    return "M3", f"M4 val PR-AUC minus M3 is {gap:.4f} (not > {CHALLENGER_MARGIN}); M3 kept"


# ------------------------------------------------------------------ metrics (A5 step 2) and thresholds (A6)
def _r(x: float) -> float:
    return round(float(x), 4)


def compute_metrics(y_true, scores, threshold: float = DECISION_THRESHOLD) -> dict:
    """accuracy, precision, recall, F1, ROC-AUC, PR-AUC, Brier and confusion [[tn, fp], [fn, tp]]."""
    y = np.asarray(y_true).astype(int)
    s = np.asarray(scores, dtype=float)
    pred = (s >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    both = len(set(y.tolist())) == 2
    return {
        "accuracy": _r(accuracy_score(y, pred)),
        "precision": _r(precision_score(y, pred, zero_division=0)),
        "recall": _r(recall_score(y, pred, zero_division=0)),
        "f1": _r(f1_score(y, pred, zero_division=0)),
        "roc_auc": _r(roc_auc_score(y, s)) if both else None,
        "pr_auc": _r(average_precision_score(y, s)) if both else None,
        "brier": _r(brier_score_loss(y, s)),
        "confusion": [[int(tn), int(fp)], [int(fn), int(tp)]],
    }


def select_thresholds(y_val, val_scores) -> dict:
    """A6. high = smallest val score whose precision >= 0.90; low = largest val score whose recall >= 0.95
    (precision_recall_curve on VALIDATION predictions). Inverted, or closer than 0.15 (or either one missing)
    -> fallback 0.35 / 0.70. Returns {low, high, source, reason, raw_low, raw_high}."""
    prec, rec, thr = precision_recall_curve(np.asarray(y_val).astype(int), np.asarray(val_scores, dtype=float))
    prec, rec = prec[:-1], rec[:-1]  # align with thr (the curve appends a (1, 0) end point)
    high_c, low_c = thr[prec >= PRECISION_TARGET], thr[rec >= RECALL_TARGET]
    raw_high = float(high_c.min()) if high_c.size else None
    raw_low = float(low_c.max()) if low_c.size else None
    base = {"raw_low": None if raw_low is None else _r(raw_low), "raw_high": None if raw_high is None else _r(raw_high)}
    if raw_high is None or raw_low is None:
        reason = "no val score reaches precision >= 0.90" if raw_high is None else "no val score keeps recall >= 0.95"
    elif raw_low >= raw_high:
        reason = "thresholds inverted (low >= high)"
    elif raw_high - raw_low < MIN_THRESHOLD_GAP:
        reason = f"gap {raw_high - raw_low:.4f} is below {MIN_THRESHOLD_GAP}"
    else:
        return {"low": _r(raw_low), "high": _r(raw_high), "source": "val_pr_curve",
                "reason": "precision/recall rules satisfied", **base}
    return {**FALLBACK_THRESHOLDS, "source": "fallback", "reason": reason, **base}
