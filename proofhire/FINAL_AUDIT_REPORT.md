# ProofHire Final Backend + AI/ML Audit Report

## A. Executive summary
**Status: PARTIALLY VERIFIED. Not signed off as fully tested.**
The sandbox used for this audit had no network access, so FastAPI, SQLAlchemy, Pydantic, bcrypt, PyJWT, PyMySQL, httpx and pytest could not be installed. The backend and ML test suites therefore were NOT run. All results below are from static review, compilation and artifact checks only.

Fixed:
1. **Security (ML endpoints):** `app/routers/ml.py::verify_internal_key` skipped the X-Internal-Key check whenever `INTERNAL_API_KEY` was empty, including in `ENV=prod`. The internal POST endpoints (/predict, /evidence, /explain, /extract-entities, /reload) could then be called by anyone. They now fail closed (401) in prod when the key is unset; dev behaviour is unchanged. Test added.
2. **Stale documentation:** `ml_gateway.py` docstring still said "INTEGRATION PENDING"; corrected.
3. **Config template:** `.env.example` now says INTERNAL_API_KEY is required in prod.

Remaining blockers: see section G.

## B. API endpoint audit (static review only; none executed)
Registered under `/api/v1` (from `app/main.py`): GET /health; POST /auth/register, /auth/login; GET /auth/me; POST, GET /assessments; POST /assessments/compare; GET, DELETE /assessments/{id}; PATCH /assessments/{id}/checklist/{item_id}; POST /reports; GET /reports/mine; GET, PATCH /admin/reports...; GET /dashboard/summary, /trends, /model-metrics. ML router under `/api/v1/ml`: model-info, metrics, predict, evidence, explain, extract-entities, reload (plus its health route).
Reviewed in code: auth (bcrypt, 72-byte limit, constant-time dummy hash, HS256-only JWT, DB-based role check), ownership rules (JWT user or X-Owner-Token hash), contact masking for non-owners, single-transaction create, route order (/compare before /{id}). No defects found in these beyond item 1 above.
I did not re-review every line of reports, admin and dashboard services; they are covered by existing tests that could not be run here.
Test outcome for every endpoint: **NOT EXECUTED in this audit.**
The guidebook PDF was not available in this session; checks used the contract notes in the repo (docs/, ML contract) and the project's recorded guidebook facts.

## C. AI/ML audit
- model.joblib SHA-256 matches `model_meta.json` (a3f4855c...9425): **verified**.
- model.joblib deserialises as an sklearn Pipeline: **verified** (under scikit-learn 1.8.0, with InconsistentVersionWarning; metadata says 1.7.2, which is the pinned runtime version, so use 1.7.2 in deployment).
- Inference, evidence, explanation, ML endpoints and gateway: **not executed** (Pydantic not installable).
- sklearn/joblib/numpy are imported lazily, so a missing model does not stop startup; gateway returns 503 model_unavailable.
- No fabricated predictions or metrics were found.

## D. Security audit
Verified by reading: password hashing, token validation (expiry, alg pinning, required claims), anonymous-owner tokens stored hashed, CORS rules in prod, secret masking in DB errors. Fixed: ML internal key fail-open in prod. Remaining risk: the `ml` router has its own copy of the key check separate from `core/deps.py` (both now behave the same way in dev; only ml.py is used by routes). No rate limiting was found in the code; confirm whether the guidebook requires it.

## E. Test results
| Item | Result |
|---|---|
| `python -m compileall -q backend ml` | passed |
| Backend `pytest` | NOT RUN (dependencies unavailable) |
| ML `pytest ml/tests` | NOT RUN (pydantic unavailable) |
| Tests added | 1 (`test_internal_key_unset_in_prod_fails_closed`), NOT RUN |
| Passed / failed / skipped | 0 / 0 / 0 executed |
| Real integration tests (MySQL, LLM) | none |
A previous report (docs/INTEGRATION_AUDIT.md) also recorded one environment-dependent ML test failure and a timeout; those were not re-checked.

## F. Changes made
- `backend/app/routers/ml.py`: fail closed in prod when key unset.
- `backend/tests/test_ml_api.py`: new test.
- `backend/app/services/ml_gateway.py`: docstring corrected.
- `backend/.env.example`: INTERNAL_API_KEY note.
- `FINAL_AUDIT_REPORT.md`: this file.

## G. Remaining limitations
Backend and ML suites unexecuted; no live MySQL; no LLM provider test; no running-server check; guidebook PDF not re-read; model not exercised under scikit-learn 1.7.2.

## H. Run instructions (from backend/, Python 3.13)
```
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # set DATABASE_URL, JWT_SECRET, ADMIN_*, INTERNAL_API_KEY
pytest -q                   # backend tests
pytest -q ../ml/tests       # ML tests
uvicorn app.main:app --host 127.0.0.1 --port 8000
```
Please run both pytest commands and send me any failures.
