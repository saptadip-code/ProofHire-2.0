#!/usr/bin/env python
"""One-command rebuild of the model artifacts in the PINNED environment (Member 1). Guidebook D2 / A12.

    PYTHONPATH=backend python ml/rebuild_artifacts.py

Runs train -> evaluate -> export in order, then re-loads the exported files with the same loader the service uses.
It REFUSES to run unless the running scikit-learn is the pinned 1.7.2 (Section 3.1), because artifacts built with any
other version are rejected by the loader at startup. Nothing is written when the check fails.
`--allow-unpinned` exists only for development sandboxes: the meta then records the real (unpinned) version.
Afterwards: `pytest ml/tests -q` and commit backend/app/ml/artifacts/ and ml/reports/.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE.parent / "backend")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import evaluate as EV  # noqa: E402
import export_artifacts as EX  # noqa: E402
import modeling as M  # noqa: E402
import train as TR  # noqa: E402
from app.ml import model_store as S  # noqa: E402


def check_pinned(running: str, allow_unpinned: bool = False) -> None:
    if running != S.REQUIRED_SKLEARN_VERSION and not allow_unpinned:
        raise SystemExit(
            f"Refusing to build: running scikit-learn {running}, pinned {S.REQUIRED_SKLEARN_VERSION} "
            "(use the Python 3.13 venv from Section 12.3: pip install -r backend/requirements.txt). "
            "Artifacts built with another version would be rejected at startup."
        )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--csv", type=Path, default=M.DEFAULT_CSV)
    ap.add_argument("--handwritten", type=Path, default=M.HANDWRITTEN_CSV)
    ap.add_argument("--artifacts-dir", type=Path, default=M.ARTIFACT_DIR)
    ap.add_argument("--reports", type=Path, default=M.REPORTS_DIR)
    ap.add_argument("--build-dir", type=Path, default=M.BUILD_DIR)
    ap.add_argument("--accept-challenger", action="store_true")
    ap.add_argument("--allow-unpinned", action="store_true", help="development only; see module docstring")
    args = ap.parse_args(argv)

    check_pinned(S.running_sklearn_version(), args.allow_unpinned)
    staging, evaluation = args.build_dir / "staging.joblib", args.build_dir / "evaluation.json"
    TR.run(args.csv, staging, args.accept_challenger)
    EV.run(staging, args.csv, args.handwritten, args.reports, evaluation)
    meta = EX.export(staging, evaluation, args.artifacts_dir)
    loaded = S.load_artifacts(args.artifacts_dir)  # final proof: the service's own startup checks pass
    print(f"OK: {loaded.meta['model_version']} built with scikit-learn {meta['sklearn_version']} "
          f"and verified by the runtime loader. Next: pytest ml/tests -q, then commit artifacts + ml/reports.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
