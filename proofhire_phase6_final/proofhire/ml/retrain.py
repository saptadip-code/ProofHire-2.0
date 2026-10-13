#!/usr/bin/env python
"""Gated retraining from approved-report feedback (Member 1). Guidebook A13. Runs on a laptop / CI, NEVER on Render.

    PYTHONPATH=backend python ml/retrain.py --feedback ml/data/feedback.csv --feedback-weight 3

Flow
  1. Read the feedback CSV (written by scripts/export_feedback.py from MySQL). Eligible rows ONLY: label == 1
     (the listing has an approved report), not a synthetic demo row, complete title/company/description, de-duplicated.
     Rows labelled 0 are DROPPED - "no report" is not proof a listing is safe, so unreported listings are never
     treated as legitimate. No eligible rows -> nothing happens.
  2. Merge with the synthetic train data via sample_weight (feedback weight, default 3), refit M3, recompute the
     thresholds and every metric (train.py / evaluate.py machinery) into a CANDIDATE directory under ml/build/.
  3. Promotion gates, ALL must pass (each is computed live on the same data for the current production model and
     the candidate, at the same 0.5 decision threshold):
       - synthetic-test PR-AUC drops by no more than 0.01
       - hand-written recall does not drop           (needs demo_data/handwritten_eval.csv)
       - pattern-holdout recall does not drop        (needs the held-out fake_offer_letter rows)
       - candidate model.joblib < 10 MB
       - `pytest ml/tests -q` passes against the candidate artifacts
     FAIL CLOSED: if a comparison cannot be computed (no hand-written file, production model cannot load, pytest not
     installed, ...) the gate FAILS and nothing is promoted. There is no override flag.
  4. Only when every gate passed: validate the candidate once more with the runtime loader, atomically replace
     backend/app/ml/artifacts/*, copy ml/reports/*, bump the version (PATCH, or MINOR if the feature set changed)
     and append a dated line to ml/CHANGELOG.md. Otherwise the production artifacts are not touched at all.
`--dry-run` evaluates everything and prints the gate table but never promotes.
Afterwards (when promoted): commit artifacts + reports + CHANGELOG and open a PR; Render redeploys from git.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, Optional

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE.parent / "backend")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402

import evaluate as EV  # noqa: E402
import export_artifacts as EX  # noqa: E402
import modeling as M  # noqa: E402
import train as TR  # noqa: E402
from app.ml import features as F  # noqa: E402
from app.ml import model_store as S  # noqa: E402

DEFAULT_FEEDBACK = HERE / "data" / "feedback.csv"
CHANGELOG = HERE / "CHANGELOG.md"
DEFAULT_FEEDBACK_WEIGHT = 3.0
PR_AUC_MAX_DROP = 0.01
FEEDBACK_REQUIRED_COLUMNS = ("title", "company_name", "description", "label")
TRUE_VALUES = {"1", "true", "yes", "y", "t"}
NULL_TOKENS = {"null", "none", "nan", "\\n", "n/a"}
NULLABLE_COLUMNS = ("requirements", "location", "salary_min", "salary_max", "contact_email", "contact_phone",
                    "company_website")
GATE_NAMES = ("synthetic_pr_auc", "handwritten_recall", "pattern_holdout_recall", "artifact_size", "ml_tests")


# ------------------------------------------------------------------ 1. feedback
def load_feedback(csv_path: Path):
    """Return (X_fb, y_fb, stats). Only label==1, non-demo, complete, de-duplicated rows survive."""
    df = M.load_dataset(csv_path)
    missing = [c for c in FEEDBACK_REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise SystemExit(f"{csv_path} is missing required columns {missing}")
    # SQL / pandas exports can write a missing value as the TEXT 'NULL', 'None', 'nan' or '\\N'. features.py would treat
    # that text as a real contact, website or requirement, so blank those optional cells before building features.
    for col in NULLABLE_COLUMNS:
        if col in df.columns:
            df[col] = df[col].where(~df[col].str.strip().str.lower().isin(NULL_TOKENS), "")
    stats = {"rows_in": int(len(df)), "dropped_synthetic_demo": 0, "dropped_not_reported": 0,
             "dropped_incomplete": 0, "dropped_duplicate": 0}

    keep = np.ones(len(df), dtype=bool)

    def drop(mask, key):
        nonlocal keep
        stats[key] += int((keep & mask).sum())
        keep &= ~mask

    if "is_synthetic_demo" in df.columns:  # demo rows are excluded (A13 step 1)
        drop(df["is_synthetic_demo"].str.strip().str.lower().isin(TRUE_VALUES).to_numpy(), "dropped_synthetic_demo")
    if "listing_id" in df.columns:  # generator rows must never come back through the feedback path
        drop(df["listing_id"].str.startswith("SYN-").to_numpy(), "dropped_synthetic_demo")
    not_reported = df["label"].str.strip() != "1"
    if "report_count_approved" in df.columns:
        counts = df["report_count_approved"].str.strip()
        not_reported |= ~counts.str.fullmatch(r"[1-9]\d*")
    drop(not_reported.to_numpy(), "dropped_not_reported")  # NEVER labelled legitimate: simply not used
    incomplete = (df["title"].str.strip() == "") | (df["company_name"].str.strip() == "") | (df["description"].str.strip() == "")
    drop(incomplete.to_numpy(), "dropped_incomplete")
    dup = df.duplicated(subset=["title", "company_name", "description"], keep="first")
    drop(dup.to_numpy(), "dropped_duplicate")

    eligible = df[keep]
    stats["eligible"] = int(len(eligible))
    if eligible.empty:
        return np.empty((0, len(F.MODEL_INPUT_COLUMNS)), dtype=object), np.empty(0, dtype=int), stats
    eligible = eligible.copy()
    eligible["label"] = "1"
    X, y = M.build_matrix(eligible)
    return X, y, stats


# ------------------------------------------------------------------ 3. gate metrics
def gate_metrics(model, csv_path: Path, handwritten_csv: Path) -> dict:
    """The three comparable numbers for ONE model: synthetic-test PR-AUC, hand-written recall, pattern-holdout recall.
    Unavailable data gives None (never 0.0), which the gates treat as 'cannot compare -> fail'."""
    df = M.load_dataset(csv_path)
    test = df[df["split"] == "test"]
    X, y = M.build_matrix(test)
    pr_auc = M.compute_metrics(y, M.positive_scores(model, X))["pr_auc"]
    hold = df[(df["split"] == "holdout") & (df["label"] == "1")]
    holdout_recall = holdout_n = None
    if len(hold):
        Xh, _ = M.build_matrix(hold)
        holdout_recall = round(float((M.positive_scores(model, Xh) >= M.DECISION_THRESHOLD).mean()), 4)
        holdout_n = int(len(hold))
    hw_recall = hw_n = None
    if handwritten_csv.is_file():
        hw = EV.evaluate_handwritten(model, handwritten_csv)
        if hw["detail"]["confusion"][1][0] + hw["detail"]["confusion"][1][1] > 0:  # at least one risky row to recall
            hw_recall, hw_n = hw["recall"], hw["n"]
    return {"synthetic_pr_auc": pr_auc, "handwritten_recall": hw_recall, "handwritten_n": hw_n,
            "pattern_holdout_recall": holdout_recall, "pattern_holdout_n": holdout_n}


def _gate(name: str, passed: bool, detail: str) -> dict:
    return {"gate": name, "passed": bool(passed), "detail": detail}


def evaluate_gates(baseline: Optional[dict], candidate: dict, candidate_model_bytes: int,
                   tests_result: tuple[bool, str]) -> list[dict]:
    """Pure gate logic. `baseline` is None when the production model could not be loaded -> every comparison fails."""
    gates = []

    def compare(name, key, allowed_drop):
        if baseline is None:
            return _gate(name, False, "production model unavailable: cannot compare (fail closed)")
        b, c = baseline[key], candidate[key]
        if b is None or c is None:
            return _gate(name, False, f"comparison data unavailable (production={b}, candidate={c}): fail closed")
        ok = c >= b - allowed_drop - 1e-9
        return _gate(name, ok, f"production {b} -> candidate {c} (allowed drop {allowed_drop})")

    gates.append(compare("synthetic_pr_auc", "synthetic_pr_auc", PR_AUC_MAX_DROP))
    gates.append(compare("handwritten_recall", "handwritten_recall", 0.0))
    gates.append(compare("pattern_holdout_recall", "pattern_holdout_recall", 0.0))
    gates.append(_gate("artifact_size", candidate_model_bytes < S.MAX_ARTIFACT_BYTES,
                       f"{candidate_model_bytes} bytes (limit {S.MAX_ARTIFACT_BYTES})"))
    gates.append(_gate("ml_tests", tests_result[0], tests_result[1]))
    return gates


def run_ml_tests(candidate_dir: Path, candidate_reports: Path) -> tuple[bool, str]:
    """`pytest ml/tests -q` against the CANDIDATE artifacts (ml/tests/conftest.py redirects the artifact and report
    directories through the PROOFHIRE_TEST_* variables). pytest missing / crash -> the gate fails."""
    env = dict(os.environ, PYTHONPATH=str(M.REPO_ROOT / "backend"),
               PROOFHIRE_TEST_ARTIFACT_DIR=str(candidate_dir), PROOFHIRE_TEST_REPORTS_DIR=str(candidate_reports))
    try:
        r = subprocess.run([sys.executable, "-m", "pytest", "ml/tests", "-q", "-p", "no:cacheprovider"],
                           cwd=M.REPO_ROOT, env=env, capture_output=True, text=True, timeout=1800)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"could not run pytest ({exc.__class__.__name__}): fail closed"
    tail = (r.stdout.strip().splitlines() or [r.stderr.strip()[-200:]])[-1][:200]
    if r.returncode == 0:
        return True, tail
    if "No module named pytest" in r.stderr:
        return False, "pytest is not installed in this environment: fail closed"
    return False, f"pytest exit code {r.returncode}: {tail}"


# ------------------------------------------------------------------ 4. promotion
def promote(candidate_dir: Path, artifacts_dir: Path) -> None:
    """Atomically replace the production artifacts with the validated candidate (meta last)."""
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=".promote_", dir=artifacts_dir))
    try:
        for name in (S.MODEL_FILENAME, S.METRICS_FILENAME, S.META_FILENAME):
            shutil.copy2(candidate_dir / name, tmp / name)
        S.load_artifacts(tmp)  # final proof with the service's own startup checks
        for name in (S.MODEL_FILENAME, S.METRICS_FILENAME, S.META_FILENAME):
            os.replace(tmp / name, artifacts_dir / name)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def changelog_line(today: dt.date, meta: dict, metrics: dict, stats: dict, weight: float) -> str:
    st = metrics["synthetic_test"]
    hw = metrics["handwritten"]
    return (f"- {today.isoformat()} | {meta['model_version']} | synthetic rows {meta['dataset']['rows']}, "
            f"feedback rows {meta['feedback_rows']} (weight {weight:g}) | synthetic test PR-AUC {st['pr_auc']}, "
            f"recall {st['recall']}, holdout recall {metrics['pattern_holdout']['recall']}, "
            f"handwritten recall {hw['recall']} (n={hw['n']}) | sklearn {meta['sklearn_version']}")


def append_changelog(path: Path, line: str) -> None:
    if not path.is_file():
        path.write_text("# ML changelog (one line per promoted model)\n\n", encoding="utf-8")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def retrain(feedback_csv: Path, weight: float = DEFAULT_FEEDBACK_WEIGHT, csv_path: Path = M.DEFAULT_CSV,
            handwritten_csv: Path = M.HANDWRITTEN_CSV, artifacts_dir: Path = M.ARTIFACT_DIR,
            reports_dir: Path = M.REPORTS_DIR, build_dir: Path = M.BUILD_DIR, changelog: Path = CHANGELOG,
            dry_run: bool = False, tests_runner: Optional[Callable[[Path, Path], tuple[bool, str]]] = None,
            today: Optional[dt.date] = None, verbose: bool = True) -> dict:
    """Returns {'promoted': bool, 'gates': [...], 'feedback': stats, 'version': str|None}. Never raises for a failed
    gate; raises SystemExit for unusable inputs (no/invalid feedback)."""
    log = print if verbose else (lambda *a, **k: None)
    if weight <= 0:
        raise SystemExit("--feedback-weight must be > 0")
    if not feedback_csv.is_file():
        raise SystemExit(f"{feedback_csv} not found; run scripts/export_feedback.py first")
    X_fb, y_fb, stats = load_feedback(feedback_csv)
    log("feedback:", stats)
    if stats["eligible"] == 0:
        raise SystemExit("no eligible feedback rows (need approved-report listings, label 1, not demo rows); "
                         "nothing was changed")

    cand = build_dir / "candidate"
    if cand.exists():
        shutil.rmtree(cand)
    cand_art, cand_rep = cand / "artifacts", cand / "reports"
    staging, evaluation = cand / "staging.joblib", cand / "evaluation.json"
    TR.run(csv_path, staging, verbose=verbose, feedback=(X_fb, y_fb, weight))
    EV.run(staging, csv_path, handwritten_csv, cand_rep, evaluation, verbose=verbose)
    meta = EX.export(staging, evaluation, cand_art, verbose=verbose, version_from=artifacts_dir)
    metrics = json.loads((cand_art / S.METRICS_FILENAME).read_text(encoding="utf-8"))

    # --- gate data: production (baseline) vs candidate, computed live on the same files
    try:
        baseline_model = S.load_artifacts(artifacts_dir).pipeline
        baseline = gate_metrics(baseline_model, csv_path, handwritten_csv)
    except S.ArtifactError as exc:
        log(f"production artifacts unusable ({exc}); comparison gates will fail closed")
        baseline = None
    cand_model = S.load_artifacts(cand_art).pipeline
    candidate = gate_metrics(cand_model, csv_path, handwritten_csv)
    size = (cand_art / S.MODEL_FILENAME).stat().st_size
    tests_ok = (tests_runner or run_ml_tests)(cand_art, cand_rep)
    gates = evaluate_gates(baseline, candidate, size, tests_ok)

    log("\npromotion gates:")
    for g in gates:
        log(f"  [{'PASS' if g['passed'] else 'FAIL'}] {g['gate']}: {g['detail']}")
    all_pass = all(g["passed"] for g in gates)
    result = {"promoted": False, "gates": gates, "feedback": stats, "version": meta["model_version"],
              "baseline": baseline, "candidate": candidate}

    if all_pass and not dry_run:
        promote(cand_art, artifacts_dir)
        reports_dir.mkdir(parents=True, exist_ok=True)
        for f in cand_rep.iterdir():
            shutil.copy2(f, reports_dir / f.name)
        append_changelog(changelog, changelog_line(today or dt.date.today(), meta, metrics, stats, weight))
        result["promoted"] = True
        log(f"\nPROMOTED {meta['model_version']}: production artifacts replaced. Commit backend/app/ml/artifacts/, "
            "ml/reports/ and ml/CHANGELOG.md and open a PR.")
    elif all_pass:
        log("\nall gates passed (dry run): NOT promoted.")
    else:
        log("\nNOT promoted: at least one gate failed. Production artifacts were not touched.")
    (build_dir).mkdir(parents=True, exist_ok=True)
    (build_dir / "retrain_report.json").write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--feedback", type=Path, default=DEFAULT_FEEDBACK)
    ap.add_argument("--feedback-weight", type=float, default=DEFAULT_FEEDBACK_WEIGHT)
    ap.add_argument("--csv", type=Path, default=M.DEFAULT_CSV)
    ap.add_argument("--handwritten", type=Path, default=M.HANDWRITTEN_CSV)
    ap.add_argument("--artifacts-dir", type=Path, default=M.ARTIFACT_DIR)
    ap.add_argument("--reports", type=Path, default=M.REPORTS_DIR)
    ap.add_argument("--build-dir", type=Path, default=M.BUILD_DIR)
    ap.add_argument("--dry-run", action="store_true", help="evaluate and print the gates; never promote")
    args = ap.parse_args(argv)
    res = retrain(args.feedback, args.feedback_weight, args.csv, args.handwritten, args.artifacts_dir, args.reports,
                  args.build_dir, dry_run=args.dry_run)
    return 0 if (res["promoted"] or args.dry_run and all(g["passed"] for g in res["gates"])) else 1


if __name__ == "__main__":
    raise SystemExit(main())
