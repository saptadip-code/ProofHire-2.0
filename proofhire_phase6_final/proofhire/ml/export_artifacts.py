#!/usr/bin/env python
"""Export the trained model + metadata + metrics to backend/app/ml/artifacts/ (Member 1). Guidebook A12.

    PYTHONPATH=backend python ml/export_artifacts.py [--bump auto|patch|minor|major] [--artifacts-dir DIR]

Reads ml/build/staging.joblib (train.py) and ml/build/evaluation.json (evaluate.py) and writes EXACTLY:
  model.joblib       joblib.dump(pipeline, path, compress=3); must be under 10 MB
  model_meta.json    {model_version, trained_at, sklearn_version, python_version, selected_model, thresholds,
                      feature_order, dataset:{type, rows, seed, generator_commit}, sha256_model, feedback_rows}
  metrics.json       exactly the metrics shape served by /ml/metrics

Version (proofhire-lr-MAJOR.MINOR.PATCH): first export 1.0.0; later exports bump PATCH (one per retrain); MINOR
(PATCH reset) when feature_order changed vs the previous meta; MAJOR only with an explicit --bump major (contract change).

Safety: the three files are first written to a temp directory and validated with the SAME loader the service uses
(model_store.load_artifacts: sklearn version, feature order, SHA-256, load, warm-up prediction). Only then are they moved
into place. Any failure leaves the existing artifacts untouched.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE.parent / "backend")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import joblib  # noqa: E402

import modeling as M  # noqa: E402
from app.ml import features as F  # noqa: E402
from app.ml import model_store as S  # noqa: E402


def next_version(previous_meta: dict | None, feature_order: list, bump: str = "auto") -> str:
    """Version bump rules (guidebook A12). `bump` in auto|patch|minor|major."""
    if bump not in ("auto", "patch", "minor", "major"):
        raise ValueError(f"unknown bump {bump!r}")
    if previous_meta is None:
        return S.format_version(1, 0, 0)
    major, minor, patch = S.parse_version(previous_meta["model_version"])
    if bump == "major":
        return S.format_version(major + 1, 0, 0)
    if bump == "minor" or (bump == "auto" and list(previous_meta.get("feature_order", [])) != list(feature_order)):
        return S.format_version(major, minor + 1, 0)
    return S.format_version(major, minor, patch + 1)


def _previous_meta(artifacts_dir: Path) -> dict | None:
    path = artifacts_dir / S.META_FILENAME
    if not path.is_file():
        return None
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
        S.parse_version(meta["model_version"])
        return meta
    except (ValueError, KeyError, S.ArtifactError):
        print(f"WARNING: previous {path} unreadable; starting again at 1.0.0")
        return None


def export(staging_path: Path, evaluation_path: Path, artifacts_dir: Path, bump: str = "auto",
           verbose: bool = True, version_from: Path | None = None) -> dict:
    """`version_from`: directory whose model_meta.json supplies the previous version (retrain.py exports its
    candidate to a temp dir but the version must continue from the PRODUCTION artifacts)."""
    log = print if verbose else (lambda *a, **k: None)
    st = joblib.load(staging_path)
    ev = json.loads(evaluation_path.read_text(encoding="utf-8"))
    if st["run_id"] != ev["run_id"] or st["csv_sha256"] != ev["csv_sha256"]:
        raise SystemExit("evaluation.json does not belong to this staging file; re-run ml/evaluate.py after ml/train.py")
    if st["feature_order"] != list(F.FEATURE_ORDER):
        raise SystemExit("features.FEATURE_ORDER changed since training; re-run ml/train.py")

    artifacts_dir.mkdir(parents=True, exist_ok=True)
    version = next_version(_previous_meta(version_from or artifacts_dir), list(F.FEATURE_ORDER), bump)

    tmp = Path(tempfile.mkdtemp(prefix=".export_", dir=artifacts_dir))
    try:
        model_path = tmp / S.MODEL_FILENAME
        joblib.dump(st["production"], model_path, compress=3)
        size = model_path.stat().st_size
        if size >= S.MAX_ARTIFACT_BYTES:
            raise SystemExit(f"model.joblib is {size} bytes, over the 10 MB limit; nothing was exported")

        meta = {
            "model_version": version,
            "trained_at": st["trained_at"],
            "sklearn_version": st["sklearn_version"],
            "python_version": st["python_version"],
            "selected_model": st["selected_model"],
            "thresholds": {"low": ev["thresholds"]["low"], "high": ev["thresholds"]["high"]},
            "feature_order": list(F.FEATURE_ORDER),
            "dataset": dict(st["dataset"]),
            "sha256_model": S.sha256_file(model_path),
            "feedback_rows": int(st["feedback_rows"]),
        }
        (tmp / S.META_FILENAME).write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        (tmp / S.METRICS_FILENAME).write_text(json.dumps(ev["metrics"], indent=2) + "\n", encoding="utf-8")

        S.load_artifacts(tmp)  # the service's own startup checks, on the candidate files
        for name in (S.MODEL_FILENAME, S.METRICS_FILENAME, S.META_FILENAME):  # meta last
            os.replace(tmp / name, artifacts_dir / name)
    except S.ArtifactError as exc:
        raise SystemExit(f"candidate artifacts failed validation; nothing was exported: {exc}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    log(f"exported {version} to {artifacts_dir}: model.joblib {size / 1024:.0f} KiB, sha256 {meta['sha256_model']}")
    return meta


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--staging", type=Path, default=M.BUILD_DIR / "staging.joblib")
    ap.add_argument("--evaluation", type=Path, default=M.BUILD_DIR / "evaluation.json")
    ap.add_argument("--artifacts-dir", type=Path, default=M.ARTIFACT_DIR)
    ap.add_argument("--bump", choices=["auto", "patch", "minor", "major"], default="auto")
    args = ap.parse_args(argv)
    for p in (args.staging, args.evaluation):
        if not p.is_file():
            raise SystemExit(f"{p} not found; run ml/train.py then ml/evaluate.py first")
    export(args.staging, args.evaluation, args.artifacts_dir, args.bump)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
