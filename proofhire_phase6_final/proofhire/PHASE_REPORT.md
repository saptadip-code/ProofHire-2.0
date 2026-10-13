# PHASE 6 (A-G6) - ML API, retraining and final validation (Member 1)

Built on `proofhire_phase5.zip`. All earlier phases and every teammate file are preserved. The trained model
(`model.joblib`, `model_meta.json`, sha256 `a3f4855c...9425`, proofhire-lr-1.0.1, scikit-learn 1.7.2) is untouched.
Older reports: `PHASE3_REPORT.md` (the previous `PHASE_REPORT.md`), `PHASE4_REPORT.md`, `PHASE5_REPORT.md`.

## What was already complete in Phase 5 (verified by reading, not rebuilt)
All eight A11 endpoints existed with real behaviour, the model lifecycle (load/validate/warm-up/reload) and the result
and LLM caches. Phase 6 verified them against the brief and tightened the gaps below.

## Changes
* `backend/app/ml/pipeline.py`: `load_model()` is now idempotent (a second call can never drop a working model); reloads
  are serialised by `_RELOAD_LOCK`; the swap stays a single assignment under `_LOCK`; reload still clears the result,
  LLM and checklist caches. No stub is ever substituted.
* `backend/app/routers/ml.py`: `If-None-Match` now accepts weak ETags (`W/"..."`), lists and `*` (was exact match only).
* `ml/retrain.py` (new): A13 gated retrain, fail closed (see `docs/ML_HANDOFF.md` section 5).
* `ml/train.py`, `ml/modeling.py`, `ml/export_artifacts.py`: optional feedback rows with `sample_weight`
  (`fit_model`, `train.run(feedback=...)`, `export(version_from=...)`); default behaviour unchanged.
* `ml/evaluate.py`: limitations now state synthetic-pattern leakage explicitly and describe feedback when it was used.
  `backend/app/ml/artifacts/metrics.json` and `ml/reports/metrics_full.json` were regenerated with the new text only
  (10 -> 11 limitation lines); no metric value changed and `model.joblib` / `model_meta.json` are byte-identical.
* Tests: new `ml/tests/test_retrain.py` (24), `ml/tests/test_runtime_imports.py` (4), 9 new router tests appended to
  `backend/tests/test_ml_api.py`; `ml/tests/conftest.py` and `ml/tests/test_artifacts.py` adjusted (candidate-artifact
  redirect for the retrain gate; `feedback_rows >= 0` instead of `== 0`).
* Docs: `docs/ML_HANDOFF.md` (new), `ml/AI_ML_INTEGRATION_CONTRACT.md` (A-G6), `ml/CHANGELOG.md` (new, baseline line only).
* No teammate-owned file was edited.

## Commands actually run (sandbox: Python 3.12, scikit-learn 1.8.0; NO pytest, pydantic, FastAPI, httpx; no network)
* Regenerated the dataset (`generate_synthetic.py --n 6000 --risky-ratio 0.38 --seed 42`): sha256 identical to the committed
  CSV and to `ml/data/README.md` (`2638fa8f...8b8c`).
* Full release dry run into temp dirs (never over the committed artifacts), `ml/rebuild_artifacts.py --allow-unpinned`:
  train M0-M4, evaluate, export, runtime-loader validation: OK. Metrics identical to the committed 1.7.2 build:
  test PR-AUC 0.9777, precision 0.9822, recall 0.8818, F1 0.9293, CV PR-AUC 0.9584 +/- 0.0094, pattern-holdout recall
  0.8616 (n=224), thresholds = fallback 0.35 / 0.70. Handwritten: null, n=0 (file not available).
* Committed artifact: `model.joblib` 57,391 bytes (< 10 MB); sha256 equals `model_meta.json`; `py_compile` of every .py: OK;
  secret scan: nothing found.
* `ml/tests` through a minimal stand-in for pytest (real pytest is not installed offline): **152 passed, 13 skipped,
  1 module could not import** (`test_ml_schemas.py`: no pydantic). Skips: 9 modules/tests that need pydantic, 3 that
  need the committed artifact to load (it is a 1.7.2 build; sandbox has 1.8.0) and the pinned-1.7.2 check.
  Retrain tests (24), runtime-import tests, training/loader/export/artifact tests all ran and passed here.
* Verified that the model loads and scores with `pandas`, `matplotlib` and `pytest` imports blocked (Render-like runtime).
  Static scan: no runtime module imports pandas or any training module.
* NOT executed anywhere by me: `backend/tests/test_ml_api.py` (needs FastAPI/httpx), the pydantic-dependent tests
  (evidence, checklist, entities, LLM client/pipeline, explainable pipeline, schemas, whole-service import test), and the
  FastAPI integration. They are compiled and statically reviewed only. The LLM-enabled-with-mocks and keys-removed
  behaviours are covered by `ml/tests/test_llm_pipeline.py` and the new router tests, which need the pinned venv to run.

## Steps you must run locally (pinned Python 3.13 / scikit-learn 1.7.2, from the repo root)
```
python -m pip install fastapi==0.142.4 "pydantic>=2.10,<3" httpx pytest pandas
set PYTHONPATH=backend            (PowerShell: $env:PYTHONPATH = "backend")
python -m pytest ml/tests backend/tests/test_ml_api.py -q
```
Expected: no failures; the pinned-version test should run (not skip). Paste any failure here.
Optional full-circle check of the gates (writes nothing to production): `python ml/retrain.py --feedback <csv> --dry-run`.

## Remaining blockers and limitations
1. `retrain.py` cannot promote until `demo_data/handwritten_eval.csv` exists (Member 4): the hand-written-recall gate fails
   closed by design. Also needs real approved-report feedback via `scripts/export_feedback.py` (Members 3/4).
2. `main.py` must include the ML router, call `load_model()` and map `ModelNotLoadedError` to 503 (Member 3); exact steps in
   `docs/ML_HANDOFF.md` section 1. I could not test integration with the real `main.py` (not in the ZIP); the router was
   only tested in a FastAPI app that mounts it the same way.
3. Thresholds are the guidebook fallback 0.35 / 0.70 (A6 rule degenerate for this bimodal model); disclosed in `limitations`.
4. Metrics are a synthetic benchmark with shared generator vocabulary (leakage) and label noise; not real-world accuracy.
5. `generator_commit` is null in `model_meta.json` (data generated outside git). Fix: commit, regenerate, rebuild with
   `python ml/rebuild_artifacts.py` on the pinned venv.
6. Deployment is Member 4's; nothing here claims it works on Render.


## Release-validation addendum (review of this ZIP after Phase 6)
Found and fixed (small, data-ingestion only; no model, feature, schema or endpoint change; `model.joblib` byte-identical):
1. `ml/retrain.py` `load_feedback()`: text tokens `NULL`, `None`, `nan`, `\N`, `N/A` in optional columns (typical SQL / pandas
   exports) were read as real contacts / websites / requirements by the features. They are now blanked first.
2. `ml/modeling.py` `load_dataset()`: Excel's plain "CSV (Comma delimited)" on Windows is cp1252 and crashed with
   `UnicodeDecodeError` (this loader also reads Member 4's `handwritten_eval.csv`). Now `utf-8-sig`, falling back to cp1252.
3. `backend/app/routers/ml.py` stale docstring; `.gitignore` now lists `ml/data/feedback.csv` (guidebook 11.3: never commit it).
Tests added: 3 in `ml/tests/test_retrain.py` (null tokens, real values kept, three CSV encodings); mutation-checked.
