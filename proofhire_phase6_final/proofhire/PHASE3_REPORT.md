# PHASE_REPORT - Phases 1-3 verification and fixes (Member 1)

## Reviewed
Uploaded ProofHire-2.0-main.zip (A-G1, A-G2, A-G3 implementation).

## Changed in this revision
- `ml/evaluate.py`: `limitations()` now also states (a) when risk thresholds are the A6 fallback, with the raw values,
  and (b) that fictional company names/phrase banks repeat across splits. Signature stays backward compatible.
- `backend/app/ml/artifacts/metrics.json` and `ml/reports/metrics_full.json`: limitations text regenerated with that
  function (8 -> 10 entries). No metric value changed; `model.joblib` and `model_meta.json` are untouched
  (sha256 a3f4855c...3425 still matches).
- `docs/AI_ML_INTEGRATION_CONTRACT.md` moved to `ml/AI_ML_INTEGRATION_CONTRACT.md` (docs/ is Member 4's); added notes on
  extra files and on the threshold fallback.
- Project root is now `proofhire/` (GitHub wrapper folder removed); this report added.

## Commands actually run (sandbox: Python 3.12, scikit-learn 1.8.0, no pytest/pydantic/FastAPI, no network)
- Regenerated the CSV with seed 42: identical sha256 (2638fa8f...8b8c).
- sha256 of model.joblib vs model_meta.json: match. `py_compile` of ml/evaluate.py: OK.
- Loaded the model bypassing the version gate (sanity only): example listings scored 0.996 (risky) / 0.045 (legit).
- NOT run: pytest suites, HTTP endpoints, retraining. Run on the pinned venv:
  `export PYTHONPATH=backend; pytest ml/tests backend/tests/test_ml_api.py -q`

## Known issues left (need your machine or a team decision)
1. Thresholds are the fallback 0.35/0.70 (A6 rule degenerate on this bimodal model): ~3% of test listings are medium.
   Decision needed: keep and disclose (done in metrics limitations), or agree a new rule + CONTRACT_CHANGELOG line.
2. `generator_commit` is null in model_meta (data generated outside git). Fix: commit, regenerate the CSV, retrain
   with `python ml/rebuild_artifacts.py` under Python 3.13 / scikit-learn 1.7.2.
3. Artifact was trained on Python 3.13.7 (target 3.13.16); loader only enforces scikit-learn, so harmless.
4. Splits are random, not by company; a company-grouped split would be a harder benchmark (future work).

## Next phase prerequisites
Phase 4 (A-G4: evidence, checklist, entities) needs `backend/app/data/checklist_library.json` from Member 4
(otherwise checklist is built against the A8 format only). Replace `pipeline.IS_STUB`/interim parts there.
