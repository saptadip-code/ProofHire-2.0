#!/usr/bin/env python
"""Evaluate the models fitted by ml/train.py (Member 1). Guidebook A5 steps 2, 4, 5 and A6.

    PYTHONPATH=backend python ml/evaluate.py [--staging ml/build/staging.joblib] [--handwritten demo_data/handwritten_eval.csv]

Writes
  ml/build/evaluation.json        hand-off to export_artifacts.py (thresholds + the exact metrics.json content)
  ml/reports/metrics_full.json    everything, incl. per-model val/test numbers and the threshold derivation
  ml/reports/confusion_matrix.png, pr_curve.png   (skipped with a message if matplotlib is missing)

Only measured numbers are written. If demo_data/handwritten_eval.csv (Member 4) does not exist, the `handwritten`
entry is {precision: null, recall: null, n: 0} and the limitations list says so - nothing is invented.
Precision / recall / F1 / accuracy / confusion use a fixed 0.5 decision threshold; risk LEVELS use the A6 thresholds.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE.parent / "backend")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import joblib  # noqa: E402
import numpy as np  # noqa: E402

import modeling as M  # noqa: E402
from app.ml import features as F  # noqa: E402

EVALUATION = M.BUILD_DIR / "evaluation.json"
SYNTHETIC_TEST_KEYS = ("precision", "recall", "f1", "roc_auc", "pr_auc", "brier", "confusion")
LISTING_COLUMNS = ("title", "company_name", "description", "label")  # minimum a hand-written CSV must have


def evaluate_handwritten(model, csv_path: Path) -> dict:
    """Precision/recall of `model` on the hand-written CSV (same columns as the synthetic CSV, A3 / D3)."""
    df = M.load_dataset(csv_path)
    missing = [c for c in LISTING_COLUMNS if c not in df.columns]
    if missing:
        raise SystemExit(f"{csv_path} is missing required columns {missing} (same columns as the synthetic CSV)")
    if df.empty:
        raise SystemExit(f"{csv_path} has no rows")
    X, y = M.build_matrix(df)
    m = M.compute_metrics(y, M.positive_scores(model, X))
    return {"precision": m["precision"], "recall": m["recall"], "n": int(len(y)), "detail": m}


def limitations(handwritten_n: int, holdout_n: int, threshold_derivation: dict | None = None) -> list[str]:
    hw = (f"Hand-written set (demo_data/handwritten_eval.csv, n={handwritten_n}) is small and written by the team; "
          "treat its precision/recall as indicative only." if handwritten_n else
          "The independent hand-written set (demo_data/handwritten_eval.csv, Member 4) was not available when these "
          "metrics were produced, so handwritten precision/recall are null (n=0).")
    th_line = None
    if threshold_derivation and threshold_derivation.get("source") == "fallback":
        th_line = (f"Risk-level thresholds are the fallback {threshold_derivation['low']} / {threshold_derivation['high']}, "
                   f"not data-derived: on validation the A6 rule gave raw low={threshold_derivation.get('raw_low')} and "
                   f"high={threshold_derivation.get('raw_high')} ({threshold_derivation['reason']}). Model scores are "
                   "strongly bimodal, so few listings fall in the medium band.")
    out = [
        "SYNTHETIC BENCHMARK: every training and test listing is machine-generated from phrase banks with fictional "
        "companies. These scores are not real-world accuracy.",
        "The generator and the evidence rules share vocabulary, so synthetic metrics are optimistic.",
        "About 2% of synthetic labels were randomly flipped (label noise), which also limits achievable precision/recall.",
        "Precision, recall, F1 and the confusion matrix use a fixed 0.5 decision threshold; risk levels use the "
        "thresholds in model_meta.json.",
        f"Pattern-holdout: fake_offer_letter listings never appear in train/val/test; recall is measured on the "
        f"{holdout_n} risky listings of that pattern.",
        hw,
        "Salary benchmarks used by the features are synthetic development medians, not verified salary data.",
        "Fictional company names and phrase banks repeat across train/val/test (no listing text is duplicated, but "
        "names are shared), so synthetic scores are optimistic; split by company would be a harder check.",
        "No real-world labelled data or user feedback has been used yet (feedback_rows = 0).",
    ]
    if th_line:
        out.insert(4, th_line)
    return out


def _plots(reports_dir: Path, cm, val_curve, test_curve, thresholds) -> list[str]:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed; skipping PNG plots")
        return []
    reports_dir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(3.6, 3.4))
    ax.imshow(np.array(cm), cmap="Blues")
    for (i, j), v in np.ndenumerate(np.array(cm)):
        ax.text(j, i, str(v), ha="center", va="center")
    ax.set_xticks([0, 1], ["pred legit", "pred risky"])
    ax.set_yticks([0, 1], ["legit", "risky"])
    ax.set_title("Synthetic test (0.5 cut-off)\nSYNTHETIC BENCHMARK", fontsize=9)
    fig.tight_layout()
    fig.savefig(reports_dir / "confusion_matrix.png", dpi=130)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(4.6, 3.6))
    for label, (p, r) in (("val (thresholds chosen here)", val_curve), ("synthetic test", test_curve)):
        ax.plot(r, p, label=label)
    ax.set_xlabel("recall")
    ax.set_ylabel("precision")
    ax.set_title(f"PR curve, synthetic benchmark\nlow={thresholds['low']} high={thresholds['high']}", fontsize=9)
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(reports_dir / "pr_curve.png", dpi=130)
    plt.close(fig)
    return ["confusion_matrix.png", "pr_curve.png"]


def run(staging_path: Path, csv_path: Path | None, handwritten_csv: Path, reports_dir: Path, out_path: Path,
        verbose: bool = True) -> dict:
    from sklearn.metrics import precision_recall_curve

    log = print if verbose else (lambda *a, **k: None)
    st = joblib.load(staging_path)
    csv_path = Path(csv_path or st["csv_path"])
    if M.sha256_file(csv_path) != st["csv_sha256"]:
        raise SystemExit("dataset CSV changed since train.py ran (sha256 differs); re-run ml/train.py")
    if st["feature_order"] != list(F.FEATURE_ORDER):
        raise SystemExit("features.FEATURE_ORDER changed since train.py ran; re-run ml/train.py")

    df = M.load_dataset(csv_path)
    parts = {n: df[df["split"] == n] for n in ("val", "test", "holdout")}
    X = {}
    y = {}
    for n, part in parts.items():
        X[n], y[n] = M.build_matrix(part)

    # --- per-model baselines (fitted on train only): val + test numbers
    baselines = {}
    for mid, model in st["models_train"].items():
        name, inputs = M.MODEL_NAMES[mid]
        baselines[mid] = {
            "name": name, "input": inputs,
            "val": M.compute_metrics(y["val"], M.positive_scores(model, X["val"])),
            "test": M.compute_metrics(y["test"], M.positive_scores(model, X["test"])),
        }

    selected = st["selected_model"]
    # --- A6 thresholds: val predictions of the selected model fitted on train only
    val_scores = M.positive_scores(st["models_train"][selected], X["val"])
    th = M.select_thresholds(y["val"], val_scores)
    thresholds = {"low": th["low"], "high": th["high"]}
    log(f"thresholds: {thresholds} ({th['source']}: {th['reason']}; raw low={th['raw_low']} high={th['raw_high']})")

    # --- headline: the PRODUCTION model (train+val refit) on the untouched test split
    prod = st["production"]
    test_scores = M.positive_scores(prod, X["test"])
    full_test = M.compute_metrics(y["test"], test_scores)
    synthetic_test = {k: full_test[k] for k in SYNTHETIC_TEST_KEYS}

    # --- pattern-holdout: recall of M3-without-fake_offer_letter on the held-out RISKY rows
    risky = y["holdout"] == 1
    if risky.any():
        hs = M.positive_scores(st["holdout_model"], X["holdout"][risky])
        holdout_recall = round(float((hs >= M.DECISION_THRESHOLD).mean()), 4)
    else:
        holdout_recall = None
    pattern_holdout = {"recall": holdout_recall, "n": int(risky.sum())}

    # --- hand-written set (Member 4); never fabricated
    hw_detail = None
    if handwritten_csv.is_file():
        hw = evaluate_handwritten(prod, handwritten_csv)
        hw_detail = hw.pop("detail")
        handwritten = {"precision": hw["precision"], "recall": hw["recall"], "n": hw["n"]}
    else:
        handwritten = {"precision": None, "recall": None, "n": 0}
        log(f"NOTE: {handwritten_csv} not found -> handwritten metrics are null (n=0)")

    metrics_json = {
        "synthetic_test": synthetic_test,
        "baselines": {mid: baselines[mid]["test"] | {"name": baselines[mid]["name"],
                                                        "val_pr_auc": baselines[mid]["val"]["pr_auc"]}
                      for mid in baselines},
        "pattern_holdout": pattern_holdout,
        "handwritten": handwritten,
        "cv": {"pr_auc_mean": st["cv"]["pr_auc_mean"], "pr_auc_std": st["cv"]["pr_auc_std"]},
        "limitations": limitations(handwritten["n"], pattern_holdout["n"], th),
    }

    v_p, v_r, _ = precision_recall_curve(y["val"], val_scores)
    t_p, t_r, _ = precision_recall_curve(y["test"], test_scores)
    plots = _plots(reports_dir, synthetic_test["confusion"], (v_p, v_r), (t_p, t_r), thresholds)

    full = {
        "run_id": st["run_id"], "trained_at": st["trained_at"], "sklearn_version": st["sklearn_version"],
        "selected_model": selected, "selection": {"reason": st["selection_reason"], "val_pr_auc": st["val_pr_auc"],
                                                   "accept_challenger": st["accept_challenger"]},
        "decision_threshold": M.DECISION_THRESHOLD,
        "thresholds": thresholds, "threshold_derivation": th,
        "splits": st["splits"], "production_train_rows": st["production_train_rows"],
        "holdout": {"fit_rows": st["holdout_train_rows"], "excluded_fake_offer_letter_rows": st["holdout_excluded_rows"],
                    "risky_rows_scored": pattern_holdout["n"], "rows_total": int(len(y["holdout"]))},
        "baselines_val_and_test": baselines,
        "cv_folds": st["cv"]["folds"],
        "production_on_test_full": full_test,
        "handwritten_detail": hw_detail,
        "plots": plots,
        "metrics_json": metrics_json,
    }
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "metrics_full.json").write_text(json.dumps(full, indent=2) + "\n", encoding="utf-8")

    handoff = {"run_id": st["run_id"], "csv_sha256": st["csv_sha256"], "thresholds": thresholds,
               "metrics": metrics_json}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(handoff, indent=2) + "\n", encoding="utf-8")

    log("synthetic_test:", json.dumps(synthetic_test))
    log("pattern_holdout:", pattern_holdout, "| handwritten:", handwritten, "| cv:", metrics_json["cv"])
    for mid, b in baselines.items():
        log(f"  {mid} val PR-AUC {b['val']['pr_auc']}  test PR-AUC {b['test']['pr_auc']}  test recall {b['test']['recall']}")
    return handoff


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--staging", type=Path, default=M.BUILD_DIR / "staging.joblib")
    ap.add_argument("--csv", type=Path, default=None, help="default: the CSV recorded in the staging file")
    ap.add_argument("--handwritten", type=Path, default=M.HANDWRITTEN_CSV)
    ap.add_argument("--reports", type=Path, default=M.REPORTS_DIR)
    ap.add_argument("--out", type=Path, default=EVALUATION)
    args = ap.parse_args(argv)
    if not args.staging.is_file():
        raise SystemExit(f"{args.staging} not found; run ml/train.py first")
    run(args.staging, args.csv, args.handwritten, args.reports, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
