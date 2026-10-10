#!/usr/bin/env python
"""Train M0..M4 offline (Member 1). Guidebook A5 training protocol steps 1-4 and 6-7.

    PYTHONPATH=backend python ml/train.py [--csv ml/data/listings_synthetic.csv] [--accept-challenger]
    PYTHONPATH=backend python ml/evaluate.py          # metrics, thresholds, reports
    PYTHONPATH=backend python ml/export_artifacts.py  # writes backend/app/ml/artifacts/*

What this does (nothing is written to backend/ - that is export_artifacts.py's job):
  1. Load the CSV (pandas); split by the `split` column; EVERY model is fitted on `train` only.
  2. Fit M0..M4; score `val` (used for model selection and thresholds). `test` and `holdout` are untouched here.
  3. 5-fold stratified CV on train for M3 (mean/std PR-AUC, random_state=42).
  4. Pattern-holdout: refit M3 on train rows WITHOUT fake_offer_letter (evaluate.py scores the held-out rows).
  6. Selection rule: M3 unless M4's VALIDATION PR-AUC beats it by more than 0.02 AND --accept-challenger is given.
  7. Refit the selected model on train+val -> the PRODUCTION model. Test stays unseen for all reported numbers.
Output: ml/build/staging.joblib (git-ignored intermediate, consumed by evaluate.py and export_artifacts.py).
"""
from __future__ import annotations

import argparse
import platform
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE.parent / "backend")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import joblib  # noqa: E402
import numpy as np  # noqa: E402
import sklearn  # noqa: E402
from sklearn.base import clone  # noqa: E402
from sklearn.metrics import average_precision_score  # noqa: E402
from sklearn.model_selection import StratifiedKFold  # noqa: E402

import modeling as M  # noqa: E402
from app.ml import features as F  # noqa: E402

STAGING = M.BUILD_DIR / "staging.joblib"


def cross_validate_m3(X, y, folds: int = 5) -> dict:
    """5-fold stratified CV on the TRAIN rows only: mean/std PR-AUC of M3."""
    skf = StratifiedKFold(n_splits=folds, shuffle=True, random_state=M.SEED)
    scores = []
    for tr, va in skf.split(X, y):
        model = clone(M.make_model("M3")).fit(X[tr], y[tr])
        scores.append(float(average_precision_score(y[va], M.positive_scores(model, X[va]))))
    return {"pr_auc_mean": round(float(np.mean(scores)), 4), "pr_auc_std": round(float(np.std(scores)), 4),
            "folds": [round(s, 4) for s in scores]}


def run(csv_path: Path, out_path: Path, accept_challenger: bool = False, verbose: bool = True) -> dict:
    log = print if verbose else (lambda *a, **k: None)
    df = M.load_dataset(csv_path)
    csv_sha = M.sha256_file(csv_path)
    prov = M.read_dataset_provenance()
    if prov["csv_sha256"] and prov["csv_sha256"] != csv_sha and Path(csv_path).resolve() == M.DEFAULT_CSV.resolve():
        log("WARNING: CSV sha256 differs from ml/data/README.md (was the CSV edited or regenerated?)")

    parts = {name: df[df["split"] == name] for name in ("train", "val", "test", "holdout")}
    if parts["train"].empty or parts["val"].empty:
        raise SystemExit("dataset has an empty train or val split; regenerate it with generate_synthetic.py")
    # Guard: nothing from the held-out pattern may be in train/val/test (A3 / A5 step 4).
    for name in ("train", "val", "test"):
        if (parts[name]["scam_pattern"] == M.HOLDOUT_PATTERN).any():
            raise SystemExit(f"{M.HOLDOUT_PATTERN} rows found in split '{name}'; the held-out pattern must stay out")
    log("split sizes:", {k: len(v) for k, v in parts.items()})

    X_tr, y_tr = M.build_matrix(parts["train"])
    X_va, y_va = M.build_matrix(parts["val"])

    # --- steps 1-2: fit M0..M4 on train, score val
    models, val_pr_auc = {}, {}
    for mid in ("M0", "M1", "M2", "M3", "M4"):
        model = M.make_model(mid).fit(X_tr, y_tr)
        models[mid] = model
        val_pr_auc[mid] = float(average_precision_score(y_va, M.positive_scores(model, X_va)))
        log(f"  {mid} fitted; val PR-AUC = {val_pr_auc[mid]:.4f}")

    # --- step 6: selection (validation only)
    selected, reason = M.select_model(val_pr_auc["M3"], val_pr_auc["M4"], accept_challenger)
    log(f"selected model: {selected} ({reason})")

    # --- step 3: CV for M3
    cv = cross_validate_m3(X_tr, y_tr)
    log("M3 5-fold CV PR-AUC:", cv["pr_auc_mean"], "+/-", cv["pr_auc_std"])

    # --- step 4: pattern-holdout model = M3 refit without fake_offer_letter
    keep = (parts["train"]["scam_pattern"] != M.HOLDOUT_PATTERN).to_numpy()
    excluded = int((~keep).sum())
    holdout_model = M.make_model("M3").fit(X_tr[keep], y_tr[keep])
    log(f"pattern-holdout M3 fitted on {int(keep.sum())} train rows ({excluded} {M.HOLDOUT_PATTERN} rows excluded)")

    # --- step 7: production = selected model refit on train+val
    X_all, y_all = np.vstack([X_tr, X_va]), np.concatenate([y_tr, y_va])
    production = M.make_model(selected).fit(X_all, y_all)
    log(f"production {selected} refit on train+val ({len(y_all)} rows)")

    staging = {
        "run_id": uuid.uuid4().hex,
        "trained_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "sklearn_version": sklearn.__version__,
        "python_version": platform.python_version(),
        "csv_path": str(csv_path),
        "csv_sha256": csv_sha,
        "dataset": {"type": "synthetic", "rows": int(len(df)), "seed": prov["seed"],
                    "generator_commit": prov["generator_commit"]},
        "feature_order": list(F.FEATURE_ORDER),
        "splits": {k: int(len(v)) for k, v in parts.items()},
        "models_train": models,
        "val_pr_auc": {k: round(v, 4) for k, v in val_pr_auc.items()},
        "selected_model": selected,
        "selection_reason": reason,
        "accept_challenger": bool(accept_challenger),
        "cv": cv,
        "holdout_model": holdout_model,
        "holdout_train_rows": int(keep.sum()),
        "holdout_excluded_rows": excluded,
        "production": production,
        "production_train_rows": int(len(y_all)),
        "feedback_rows": 0,  # no feedback merged until A-G6 retrain.py
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    (out_path.parent / ".gitignore").write_text("*\n!.gitignore\n", encoding="utf-8")
    joblib.dump(staging, out_path, compress=3)
    log(f"staging written: {out_path} ({out_path.stat().st_size / 1024:.0f} KiB)")
    return staging


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--csv", type=Path, default=M.DEFAULT_CSV)
    ap.add_argument("--out", type=Path, default=STAGING)
    ap.add_argument("--accept-challenger", action="store_true",
                    help="team agrees to give up coefficient-based evidence if M4 wins the A5 selection rule")
    args = ap.parse_args(argv)
    run(args.csv, args.out, args.accept_challenger)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
