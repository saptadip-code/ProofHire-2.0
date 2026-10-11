# AI/ML Integration Contract (Member 1)

Documents the guidebook contract; it never overrides it. Status: `implemented` / `pending` / `blocked`.
Last updated: Phase 3 (A-G3), 2026-10-10. **A-G3: the score / level / thresholds / model_version are REAL (trained M3). Evidence, checklist, entities (email only) and explanation are still INTERIM (A-G4 / A-G5)** and are returned empty / fixed-template, never fabricated.

## Endpoints (prefix `/api/v1/ml`, mounted by `main.py`: `app.include_router(ml.router, prefix='/api/v1/ml')`)

| Method + path | Auth | Status (A-G3) | Behaviour |
|---|---|---|---|
| GET `/health` | none | implemented | real `{loaded, model_version, trained_at, sklearn_version (running), llm_enabled, llm_circuit_open:false}` |
| GET `/model-info` | none | implemented | `model_meta.json` of the LOADED model; `Cache-Control: public, max-age=300`, `ETag: "<sha256_model>"`, 304 on `If-None-Match`; 503 `model_unavailable` if not loaded |
| GET `/metrics` | none | implemented | `metrics.json`; same cache headers, ETag = sha256 of the JSON; 503 if not loaded / missing |
| POST `/predict` | X-Internal-Key | implemented (real) | `{risk_score, risk_level, thresholds, model_version}` via `pipeline.predict_listing()`; no evidence, no LLM, no DB; 503 if model not loaded |
| POST `/evidence` | X-Internal-Key | partial | real score/level; `evidence: []` until A-G4; header `X-ProofHire-Stub: true`; 503 if not loaded |
| POST `/explain` | X-Internal-Key | partial | real score/level; interim template text, empty evidence/checklist; header `X-ProofHire-Stub: true`; 503 if not loaded |
| POST `/extract-entities` | X-Internal-Key | partial | interim: normalised email only (needs no model); header `X-ProofHire-Stub: true` |
| POST `/reload` | X-Internal-Key | implemented | validates the new artifact first, swaps atomically, `{reloaded:true, model_version, sha256}`; 500 `internal_error` and OLD model kept if invalid |

Auth: env `INTERNAL_API_KEY` empty -> check skipped; otherwise missing/wrong `X-Internal-Key` -> 401 `unauthorized` (Section 5.5 body). Implemented.
Cache headers/ETag for model-info and metrics: implemented (A-G3).

## Schemas (`backend/app/schemas/ml_schemas.py`) — implemented
Enums (5.1): `WorkMode, EmploymentType, PayPeriod, ApplicationChannel, InterviewMode, RiskLevel, EvidenceType, EvidenceDirection, ExplanationSource, SignalType`.
`ListingInput` (5.2, all fields/limits/defaults). Result parts: `Thresholds, EvidenceItem{id,code,label,type,direction,severity,snippet,weight}, KeyConcern, Explanation{source,summary,key_concerns,what_to_verify}, ChecklistItem{code,text,priority,done}, Entity{type,value}, LlmMeta{provider,model,latency_ms,success,error_code}, MlResult`.
Also provided for convenience (backend may import instead of redefining): `AssessmentChecklistItem, Connection, AssessmentResult`.
Endpoint models: `MlHealthResponse, PredictResponse, EvidenceResponse, ExtractEntitiesResponse, ReloadResponse`.

## Python contract (`backend/app/ml/pipeline.py`) — signatures frozen (unchanged since Phase 1)
- `assess_listing(listing: ListingInput, with_llm: bool = True) -> MlResult` — real score; interim evidence/checklist/explanation; raises `ModelNotLoadedError` when no valid model (backend maps to 503 `model_unavailable`). No fallback / stub model exists.
- `load_model() -> None` (never raises; failure -> `model_status()["loaded"] is False`), `reload_model() -> dict` (returns the new `model_meta` dict; raises `ModelNotLoadedError`, old model kept), `model_status() -> dict` `{loaded, model_version, trained_at, sklearn_version, llm_enabled}` — implemented.
- Not in guidebook A2 (added, flagged): `llm_circuit_open()` (stub until A-G5), `get_model_info()`, `get_metrics()` (Part B references it), `predict_listing()` (score only, for `/ml/predict`), `interim_entities()` (until A-G4), `get_load_error()` (diagnostics), `ModelNotLoadedError`, `IS_STUB` (True until A-G4/A-G5), `_reset_for_tests()`.
- `backend/app/ml/entities.py::FREE_MAIL_DOMAINS` — implemented; `extract_entities()` pending A-G4.
- Backend: `POST /assessments` should catch `ModelNotLoadedError` -> 503 `model_unavailable` (Section 5.5), or check `model_status()["loaded"]`.

## Model / artifact contract (A-G3) — implemented
Files (M1-owned): `ml/modeling.py` (shared helpers), `ml/train.py`, `ml/evaluate.py`, `ml/export_artifacts.py`, `backend/app/ml/model_store.py` (pydantic-free loader/validator, imported by `pipeline.py`), `backend/app/ml/artifacts/{model.joblib, model_meta.json, metrics.json}`, `ml/reports/{metrics_full.json, confusion_matrix.png, pr_curve.png}`.
Commands: `PYTHONPATH=backend python ml/train.py && python ml/evaluate.py && python ml/export_artifacts.py` (git-ignored intermediates in `ml/build/`).
Models (A5, exact hyper-parameters): `M0` Dummy(stratified), `M1` LR on TF-IDF, `M2` RandomForest (structured), `M3` LR on TF-IDF + scaled numeric + binary + one-hot (PRODUCTION), `M4` HistGradientBoosting (structured). Selection: M3 unless M4 val PR-AUC > M3 + 0.02 AND `--accept-challenger`; validation numbers only. Production = selected model refit on train+val; test untouched.
Model input contract: `features.MODEL_INPUT_COLUMNS = [TEXT_COL] + FEATURE_ORDER` (27 columns) and `features.model_input_values(listing)`; used by BOTH training and inference. ColumnTransformer step names are `tfidf, num, bin, cat`; columns are selected by POSITION (not name) so inference needs no pandas.
`model_meta.json` keys (exact): `model_version, trained_at, sklearn_version, python_version, selected_model, thresholds{low,high}, feature_order, dataset{type,rows,seed,generator_commit}, sha256_model, feedback_rows`. `feature_order` = `FEATURE_ORDER` (26 structured columns, see open item 5). `dataset.rows` = rows in the CSV (6,000). `generator_commit` = value recorded in `ml/data/README.md` (null if unknown).
`metrics.json` keys (exact, A11): `synthetic_test{precision,recall,f1,roc_auc,pr_auc,brier,confusion}`, `baselines{M0..M4}`, `pattern_holdout{recall,n}`, `handwritten{precision,recall,n}`, `cv{pr_auc_mean,pr_auc_std}`, `limitations[str]`. Guidebook leaves the `baselines.Mx` contents open: each is `{accuracy, precision, recall, f1, roc_auc, pr_auc, brier, confusion, name, val_pr_auc}` on the test split (new, flagged). `handwritten` is `{null, null, 0}` until `demo_data/handwritten_eval.csv` exists (BLOCKED on Member 4).
Version: `proofhire-lr-MAJOR.MINOR.PATCH`; first export 1.0.0, then PATCH per export, MINOR (patch reset) when `feature_order` changed vs the previous meta, MAJOR only via `export_artifacts.py --bump major`.
Thresholds (A6): `high` = smallest val score with precision >= 0.90, `low` = largest val score with recall >= 0.95 (val PR curve of the selected model fitted on train only); inverted, gap < 0.15 or missing -> 0.35 / 0.70. Levels: `score >= high` high, `score < low` low, else medium (score rounded to 4 dp first).
Startup validation (`model_store.load_artifacts`, A12): meta keys/format -> `sklearn_version` == RUNNING scikit-learn -> `feature_order` == `FEATURE_ORDER` -> `sha256_model` (checked BEFORE unpickling) -> `joblib.load` -> warm-up prediction in [0,1]. Any failure: `loaded=false`, no fabricated model. `REQUIRED_SKLEARN_VERSION = "1.7.2"` is checked by `ml/tests/test_artifacts.py` and logged as a warning at load.

## Dataset contract (A-G2) — implemented
`ml/data/generate_synthetic.py` — `PYTHONPATH=backend python ml/data/generate_synthetic.py --n 6000 --risky-ratio 0.38 --seed 42 --out ml/data/listings_synthetic.csv` (also writes `ml/data/README.md` with seed, commit hash, sha256, counts).
Columns (exact, in order, A3): `listing_id, title, company_name, description, requirements, location, work_mode, employment_type, salary_min, salary_max, pay_period, contact_email, contact_phone, application_channel, company_website, upfront_fee_amount, interview_mode, scam_pattern, difficulty, label, split`.
Values: `scam_pattern` in `legit, advance_fee, data_harvest, unrealistic_pay, ghost_company, mlm_pyramid, fake_offer_letter`; `difficulty` in `easy, subtle, messy`; `label` 1=risky 0=legit; `split` in `train, val, test, holdout`. Optional fields are empty strings; salary 0 = not stated.
Actual counts (seed 42): 6,000 rows; label=1 2,306 (38.43%) after 120 noise flips; pre-noise risky 2,280 = advance_fee 684 / unrealistic_pay 456 / data_harvest 342 / ghost_company 342 / mlm_pyramid 228 / fake_offer_letter 228; subtle 342; messy 372; splits train 4,040 / val 865 / test 867 / holdout 228 (= all `fake_offer_letter`).
`ml/data/lexicons.py` — implemented (fictional companies, 16 roles, 3 paraphrase banks per phrase type, runtime lexicon source; `python ml/data/lexicons.py --export-runtime` regenerates the two JSON files).

## Feature contract (A-G2) — `backend/app/ml/features.py` — implemented
Public: `NUM_COLS, BIN_COLS, CAT_COLS, TEXT_COL, FEATURE_ORDER, CAT_VALUES, build_row(listing) -> dict, text_of(listing) -> str`.
`FEATURE_ORDER` (26 structured columns, A4 order): `salary_max_month_log, salary_ratio_vs_role, salary_spread, desc_words, req_words, exclaim_count, caps_ratio, urgency_hits, fee_amount_log` | `has_upfront_fee, asks_personal_data, guaranteed_claim, no_experience_hype, email_is_free, email_present, website_missing, domain_mismatch, messaging_only, no_interview, vague_desc, vague_requirements, phone_present` | `work_mode, employment_type, application_channel, interview_mode` (one-hot by the sklearn pipeline in A-G3). TF-IDF column name: `text` (`TEXT_COL`).
Runtime data (M1-owned, `backend/app/data/`): `role_benchmarks.json` (labelled `synthetic`), `lexicons_runtime.json`. Inference path imports only stdlib + `app.ml.entities` (no pandas/numpy/sklearn/pydantic; tested).
Added identifiers (NOT in guidebook; flagged): `build_model_row()`, `raw_text_of()`, `search_lexicon()`, `urgency_matches()`, `detect_role()`, `benchmark()`, `to_monthly()`, `TEXT_COL`, `CAT_VALUES`; JSON keys `urgency_phrases, fee_patterns, personal_data_patterns, guaranteed_claim_patterns, no_experience_patterns, negation_pattern` and `_meta/default/roles[{role,keywords,monthly_median_inr}]`.

## Pending (later phases)
18 evidence codes (A-G4), checklist + entities (A-G4), LLM client / template explainer / guardrails / LLM + result caches (A-G5/A-G6), retrain gate + feedback (A-G6), real hand-written evaluation (needs Member 4's file).

## Environment variables
Read now: `INTERNAL_API_KEY`, `LLM_ENABLED` (health only). Other `LLM_*` vars: pending A-G5. Phase 3 adds none.

## Ownership / dependencies
Owned by M1: `ml/**`, `backend/app/ml/**`, `routers/ml.py`, `schemas/ml_schemas.py`, the two data JSONs. Package `__init__.py` files under `backend/app/` were created only so tests import; M3's versions take precedence on merge.
Backend must: register the router in `main.py`; call `load_model()` in lifespan (it never raises); return 503 `model_unavailable` from `POST /assessments` on `ModelNotLoadedError`.
Read-only for M1: `checklist_library.json` (M4), all other backend files (M3).

## Open items / conflicts
1. No project ZIP was supplied; built from the guidebook alone. Re-check against real `main.py`, `core/errors.py` when available.
2. Section 5.5 error body is emitted locally by the router (no `AppError` available); 422 wrapping stays with M3's handler.
3. `get_metrics()` referenced in Part B but absent from A2 (ambiguity).
4. `model_version` stub value `proofhire-lr-0.0.0` is a placeholder, not a trained model.
5. (A-G2) `FEATURE_ORDER` ambiguity: guidebook says "keep FEATURE_ORDER as a constant" and also lists a TF-IDF text feature. Chosen: FEATURE_ORDER = the 26 structured columns; text is `TEXT_COL`. Confirm before A-G3 writes `model_meta.json.feature_order`.
6. (A-G2) Guidebook gives no field names for the two runtime JSON files; the keys above are new, documented identifiers.
7. (A-G2) A3 says descriptions are 50-250 words, so even `messy` rows are >= 50 words and `vague_desc` (< 40 words) never fires in the synthetic data; the observed VAGUE_DESCRIPTION rule still works at inference.
8. (A-G2) `one_time` pay period is compared to the monthly benchmark as stated (guidebook only defines year -> /12).
9. (A-G2) Label noise flips can land on `holdout` rows (4 of 228 are label 0); pattern-holdout recall in A-G6 should use label==1 rows.
10. Environment: authored/tested on Python 3.12 + scikit-learn 1.8 sandbox, not the pinned 3.13.16 / 1.7.2; real `pytest` and `pydantic` were unavailable offline (see handoff).
11. (A-G3) ENVIRONMENT MISMATCH: the committed artifact was trained in a sandbox with Python 3.12.3 / scikit-learn **1.8.0**, not the pinned 3.13.16 / **1.7.2**. By the A12 rule the loader REJECTS it on a 1.7.2 runtime (`/ml/health` `loaded:false`, assessments 503) until it is re-exported there. Retrain in the pinned venv with ONE command, `PYTHONPATH=backend python ml/rebuild_artifacts.py` (refuses to run on any other scikit-learn, runs train -> evaluate -> export, then re-validates with the runtime loader), and commit the new artifacts (version becomes 1.0.1 by the PATCH rule). The sandbox had no network, so this could not be done here.
12. (A-G3) A6 thresholds literally applied gave `0.1409 / 0.1758` (gap 0.035 < 0.15), so the guidebook fallback **0.35 / 0.70** is what ships. The literal rules (smallest score with precision >= 0.90; largest score with recall >= 0.95) tend to land close together or inverted for strong models; flag to the team if different rules are wanted (contract change).
13. (A-G3) Guidebook gives no decision threshold for precision/recall/F1/confusion: fixed 0.5 used (stated in `limitations`). Pattern-holdout recall = recall at 0.5 on the label==1 `fake_offer_letter` rows, scored by M3 refit without that pattern (train already excludes it).
14. (A-G3) `handwritten_eval.csv` (Member 4, D-G3) does not exist: `handwritten` is `{precision:null, recall:null, n:0}`. `evaluate.py` scores it automatically once the file is present (same columns as the synthetic CSV).
15. (A-G3) `ColumnTransformer` selectors are integer positions into `MODEL_INPUT_COLUMNS` instead of the column names shown in A5, because name-based selection requires a pandas DataFrame at inference (forbidden by D5/A14). Step names, transformers and hyper-parameters are unchanged.
16. (A-G3) `backend/tests/test_ml_api.py` and `ml/tests/test_ml_schemas.py` were updated (stub assertions removed). They need real `fastapi`/`pydantic`/`pytest` and were NOT executed in the authoring sandbox.
17. (A-G3) No result cache / LLM cache yet (A12); `reload_model()` has a `_clear_caches()` hook for them.

## Files beyond the guidebook A1 table (all inside Member 1 directories)
- `ml/modeling.py` - shared offline helpers (model factory M0..M4, metrics, A6 thresholds); offline only.
- `ml/rebuild_artifacts.py` - train -> evaluate -> export in one command; refuses to run unless scikit-learn is 1.7.2.
- `backend/app/ml/model_store.py` - artifact validation/loading/scoring (no pandas, no pydantic); wrapped by `pipeline.py`.
- This document lives in `ml/` (not `docs/`, which belongs to Member 4); copy it into `docs/` by agreement if wanted.

## Known state of the thresholds (Phase 3)
`thresholds` in `model_meta.json` are the A6 FALLBACK 0.35 / 0.70: the literal A6 rule gave raw 0.1413 / 0.1752 on
validation (gap < 0.15). Result on the synthetic test split: ~3% of listings are `medium`. Changing the rule needs a
team agreement and a `docs/CONTRACT_CHANGELOG.md` line; it has NOT been changed.
