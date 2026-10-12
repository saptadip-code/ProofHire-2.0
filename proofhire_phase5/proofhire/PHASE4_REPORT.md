# PHASE 4 (A-G4) - Explainable risk assessment (Member 1)

Built on `proofhire_phase3_fixed.zip`. The real model, schemas, training pipeline, artifacts, router and teammate
files are preserved. Contract details: `ml/AI_ML_INTEGRATION_CONTRACT.md` ("Explainability contract (A-G4)").

## Files
Added: `backend/app/ml/evidence.py`, `backend/app/ml/checklist.py`, `backend/app/ml/template_explainer.py`,
`ml/tests/test_evidence.py`, `ml/tests/test_checklist.py`, `ml/tests/test_entities.py`,
`ml/tests/test_pipeline_explainable.py`, this report.
Modified: `backend/app/ml/entities.py` (extract_entities + normalisers; `FREE_MAIL_DOMAINS` unchanged),
`backend/app/ml/pipeline.py` (evidence/checklist/entities/template integration, result cache, `IS_STUB=False`,
`interim_entities` removed), `backend/app/routers/ml.py` (/extract-entities uses A9, stub header gone),
`ml/AI_ML_INTEGRATION_CONTRACT.md`, and three Phase 3 tests that asserted the interim behaviour
(`backend/tests/test_ml_api.py`, `ml/tests/test_pipeline_model.py`, `ml/tests/test_ml_schemas.py`).
Untouched: features.py, model_store.py, artifacts, training/evaluation code, schemas, data JSONs, everything of
Members 2-4.

## Implemented evidence codes (17 observed + 2 model codes)
UPFRONT_FEE, PERSONAL_DATA_REQUEST, GUARANTEED_OFFER_CLAIM, UNREALISTIC_PAY, FREE_EMAIL_CONTACT,
EMAIL_DOMAIN_MISMATCH, NO_COMPANY_WEBSITE, MESSAGING_APP_ONLY, URGENCY_PRESSURE, NO_INTERVIEW, VAGUE_DESCRIPTION,
VAGUE_REQUIREMENTS, EXCESSIVE_HYPE, CORP_EMAIL_MATCHES_WEBSITE, DETAILED_REQUIREMENTS, STRUCTURED_INTERVIEW,
PAY_IN_EXPECTED_RANGE, MODEL_TERM, MODEL_FEATURE. Each observed code has a firing test, a not-firing test, and
guidebook attributes (severity, direction, null weight) asserted; threshold boundaries are tested separately.
("18 codes" in the guidebook = 17 observed + the single MODEL_TERM/MODEL_FEATURE table row.)

## Tests actually run
Environment: Python 3.13, scikit-learn 1.7.2 (the pinned version, so the committed artifact loads), pydantic 2.14,
FastAPI 0.142.4, pandas, pytest 9.1.1.
`PYTHONPATH=backend pytest ml/tests backend/tests -q` -> **364 passed, 1 skipped** (baseline before the phase:
130 passed, 6 skipped; the extra 6 ran once pandas was installed). The skip is the check on Member 4's real
`checklist_library.json`, which is not in the repository.
Mutation check (deliberately broke the code, confirmed the tests fail): ratio threshold, top-negative count,
snippet casing, the 12 cap, free-mail email_domain, always-on cap, cache TTL, cache max entries, cache key
ignoring LLM mode, cache key ignoring thresholds, risk level hard-coded. All 11 were detected.
Measured: uncached `assess_listing` about 5 ms median (9 ms max over 60 calls).
NOT run: a live server with Member 3's real `main.py` and database; Groq/LLM (A-G5); retraining.

## Decisions and open points for you
1. **12-item cap vs model evidence.** Following A7 literally (observed first, truncate the tail), a listing that
   fires 12 or more observed rules gets no model evidence, and 11 hits leave one slot. Observed items are never
   displaced. If you want guaranteed model slots (for example cap observed at 8-10) that is a contract change.
2. **Model signals are mostly structured features,** and some have counter-intuitive signs learned from synthetic
   data (for example "a contact email is given" raises risk about +1.1 logit on a clean listing). TF-IDF terms
   contribute little (max about 0.2). Contributions are verified to reproduce the score exactly; labels say
   "Model signal" / "Wording" and never state facts about the employer.
3. **Snippets:** text rules quote exact spans of the submitted text; email rules quote the submitted email with
   its original case; field-only rules (pay, channel, interview, website, the fee amount field) have a null
   snippet. Nothing is composed.
4. **Checklist library missing.** Until Member 4 delivers `backend/app/data/checklist_library.json`, `checklist`
   is `[]`, an ERROR is logged once, and `checklist.library_status()` reports `missing`. No substitute content is
   invented. Unknown trigger codes in their file are reported (item kept).
5. **`template_explainer.py`** is a minimal deterministic version created now so concerns can cite real evidence
   ids; A-G5 owns any further work on it. `with_llm` still has no effect (explanation is always the template).
6. **Cache:** SHA-256 of the normalised listing JSON plus model version/hash, thresholds and the effective LLM
   mode; 100 entries, 600 s TTL, deep copies, cleared on reload. A-G5 must not cache a template fallback under
   the LLM-enabled key.
7. **Behaviour changes for Backend/Frontend:** `X-ProofHire-Stub` header is gone; `/ml/extract-entities` now
   returns email, email_domain, phone, website_domain and company_name entities per A9.

## Environment / setup
No new dependencies and no new environment variables. Run the committed artifact on scikit-learn 1.7.2 (the
loader rejects other versions, as in Phase 3). Command:
`PYTHONPATH=backend pytest ml/tests backend/tests -q`.

## Next phase (A-G5) prerequisites
Groq key in the environment (`LLM_*` variables per A10), `with_llm` wiring in `assess_listing`, evidence-id
validation of LLM output against the ids produced here, circuit breaker and LLM cache. Member 4's checklist
library is needed for a complete end-to-end demo.
