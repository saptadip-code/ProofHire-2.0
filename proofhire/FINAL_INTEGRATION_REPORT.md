# ProofHire - Final Integration Report

**Read this first: what was and was not verified.** The environment used for this integration had **no network access** and no
`fastapi`, `sqlalchemy`, `pydantic` or `pytest` installed, and no frontend dependencies (`vite`, `react`). Therefore:
the backend test suite, the ML test suite, the frontend build, the integration smoke test and browser tests were **NOT run**.
What was run: Python byte-compilation, the 30 dependency-free frontend tests, and the new checklist-library tests (run directly, without pytest).
Everything in the API matrix below is a **static comparison of source code against source code and the guidebook**, not a live request/response test.

## 1. Project overview
- Frontend: React 19 + Vite, plain JavaScript, `react-router-dom`, Recharts, Lucide (`frontend/`). Existing UI preserved.
- Backend: FastAPI + SQLAlchemy + PyMySQL, JWT (HS256) + bcrypt, all routes under `/api/v1` (`backend/`). ML package in-process (`backend/app/ml/`), offline training in `ml/`.
- Structure follows guidebook Section 4: `backend/ frontend/ ml/ docs/ scripts/ render.yaml`.
- Approach: the backend's registered routes and Pydantic schemas were the reference (they already match guidebook Sections 5/6); the frontend was corrected to match them. No endpoint or schema was changed.
- Neither original ZIP was overwritten.

## 2. Guidebook compliance
Checked statically: endpoint table (5.4), error envelope (5.5), enums (5.1), ListingInput payload (5.2), CORS rules (B5), env vars (B2), ML endpoint list (A11), frontend API client rules (C1), routes (C2), repo layout (Section 4).
- Satisfied (by inspection): all 5.4 endpoints are registered under `/api/v1`; ML router mounted at `/api/v1/ml` with the 8 A11 endpoints; CORS reads `CORS_ORIGINS`, `allow_credentials=False`; frontend client sends `Authorization: Bearer`, `X-Owner-Token`, 20 s timeout, parses the 5.5 error shape, uses `ph_token / ph_user / ph_owner_tokens`; frontend `toPayload` sends integers and `null` for blank optionals; `POST /reports` and `POST /assessments/compare` ids are sent as numbers.
- Deviations / gaps:
  - `frontend/package.json` uses `latest` for react-router-dom, recharts, vite and has no Tailwind 4 (guidebook 3.1/3.4 and C-stack). Existing hand-written CSS was preserved; not changed (a change risks the UI and could not be build-tested).
  - Runtime pins: guidebook requires Python 3.13.16 / scikit-learn 1.7.2. The sandbox had Python 3.12 and scikit-learn 1.8.0, so model-artifact tests would be expected to fail here regardless of code correctness.
  - `backend/requirements.lock.txt` (B1), `backend/certs/aiven-ca.pem` (public cert from the Aiven console), `demo_data/*`, `scripts/seed_demo.py`, `scripts/export_feedback.py`, `scripts/warm_up.sh`, `backend/app/db/feedback_query.sql` and `docs/pitch/*` are **not present in the supplied ZIPs and were not created** (they need a real environment, the Aiven console or the team's own content). `ml/data/listings_synthetic.csv` / handwritten eval set are likewise out of scope.
  - `metrics.json` has `handwritten` = null (n=0) because Member 4's 60-row set did not exist (stated in its own limitations text, which the dashboard shows).

## 3. API integration matrix (static comparison; "live test" = not run)
| Frontend feature | Endpoint | Auth | Compatibility finding | Live test |
|---|---|---|---|---|
| Register / Login | POST `/auth/register`, `/auth/login` | none | Body and `{access_token, user}` handling match | not run |
| Session restore, route protection | GET `/auth/me` | user | 401 clears the token (client + AuthContext) | not run |
| Analyse listing | POST `/assessments` | optional | Payload matches ListingInput; owner_token saved | not run |
| Report page | GET `/assessments/{id}` | owner / id | `normalizeAssessment` matches AssessmentResult | not run |
| Saved list / filter / delete | GET `/assessments`, DELETE `/assessments/{id}` | user / owner | `{items,total,page,limit}` matches; limit 50 <= backend max | not run |
| Checklist toggle | PATCH `/assessments/{id}/checklist/{item_id}` | owner / token | `{done}` -> `{id,done}` matches | not run |
| Compare | POST `/assessments/compare` | none | **DEFECT FIXED**: response `a`/`b` are flat summaries (`id,title,company_name`), the page read `assessment_id` and `listing.title` | not run |
| Report listing | POST `/reports`, GET `/reports/mine` | optional / user | matches | not run |
| Admin moderation | GET/PATCH `/admin/reports` | admin | matches; role enforced by backend | not run |
| Dashboard summary | GET `/dashboard/summary` | none | **DEFECT FIXED**: reader looked for `risk_distribution`; backend sends `by_level`; high-risk count now taken from `by_level.high` | not run |
| Model metrics / confusion matrix | GET `/dashboard/model-metrics` | none | **DEFECT FIXED**: reader looked at `test`/`holdout`; real shape is `synthetic_test` with `confusion:[[tn,fp],[fn,tp]]`; the metrics card and matrix would have shown "not available" | not run |
| Trends | GET `/dashboard/trends` | none | matches | not run |
| Wake banner | GET `/health` | none | matches | not run |
| ML endpoints `/ml/*` | not called by the frontend | X-Internal-Key | By design (A11: backend imports `assess_listing()`); frontend does no inference | not run |

## 4. AI/ML integration status
- No frontend inference logic exists; the UI only renders results returned by `POST /assessments` (score, evidence, explanation, checklist, entities, connections).
- Model artifacts present in `backend/app/ml/artifacts/` (`model.joblib`, `model_meta.json`, `metrics.json`). Their sha256 and sklearn-version check were **not executed** here.
- **Defect fixed (data, not code):** `backend/app/data/checklist_library.json` (Member 4, required by A8) was missing, so every assessment returned an empty checklist. A 23-item library was authored per D2 (fees, identity documents, MCA search, domain age, recruiter verification, contract review, OTP, safe payment, cybercrime.gov.in / helpline 1930), all triggers are valid A7 codes, 4 always-on items. Also added `moderation_policy.json` (6 report types, acceptance rule and 3 rejection reasons each). **Review the wording with the team**; it was written by the integrator, not the owner.
- Mocked vs real: nothing was run. Existing backend tests use a fake ML package by design.
- Limitations unchanged from `metrics.json`: synthetic benchmark only, optimistic metrics, thresholds are the 0.35/0.70 fallback.

## 5. Authentication and security
- JWT bearer; token in `localStorage['ph_token']`; 401 on any authenticated request emits a session-expired event and clears state; protected routes are frontend-only convenience, backend enforces roles.
- CORS: explicit origins from `CORS_ORIGINS`; no `*` in the code paths reviewed. No secrets found in the frontend or ZIP (scan for key patterns; `.env` files excluded; `.env.example` files contain no values).
- Risks: localStorage tokens are readable by XSS (as designed by the guidebook); untested rate limiter and role checks at runtime.

## 6. Changes made
- `frontend/src/api/dashboard.js` - summary and metrics readers aligned to the backend shapes.
- `frontend/src/pages/Compare.jsx`, `frontend/src/components/CompareTable.jsx` - read flat AssessmentSummary fields (old `listing.*` fallbacks kept).
- `frontend/tests/lib.test.js` - 2 new tests built from the real backend/metrics shapes.
- `backend/app/data/checklist_library.json`, `moderation_policy.json`, `backend/tests/test_checklist_library.py` - new (see section 4).
- `render.yaml` (verbatim from guidebook 13.3), `scripts/e2e_smoke.py` (new, **never run**), `docs/CONTRACT_CHANGELOG.md` (one line appended).
- Unchanged: backend code, ML code, database models, UI styling.

## 7. Test results (actual)
| Check | Command | Result |
|---|---|---|
| Frontend unit tests | `cd frontend && npm test` (node --test) | 30 run, 30 passed, 0 failed, 0 skipped |
| Python syntax | `python3 -m compileall backend/app ml backend/tests` | OK |
| Smoke script syntax | `python3 -m py_compile scripts/e2e_smoke.py` | OK (not executed) |
| Checklist/moderation library | 6 test functions run directly with Python (pytest unavailable) | 6 passed |
| Backend pytest | `cd backend && pytest -q` | **BLOCKED** (no fastapi/sqlalchemy/pytest, no network) |
| ML pytest | `PYTHONPATH=backend pytest ml/tests -q` | **BLOCKED** |
| Frontend build / lint | `npm ci && npm run build` | **BLOCKED** (no network) |
| E2E smoke, browser tests | `scripts/e2e_smoke.py`, browser | **NOT RUN** |
Earlier reports in `docs/` claim backend passes (e.g. 327 tests); those were not reproduced here.

## 8. Known issues / unverified
Everything marked not run above; JSX files were not compiled; real MySQL not exercised (backend tests use SQLite); LLM path unexercised; the admin card does not display `listing_title`/`company_name` returned by the API (cosmetic); frontend dependency versions use `latest`.

## 9. Setup and execution (guidebook Section 12)
1. MySQL: run the SQL from guidebook B7 (or the Docker command).
2. Backend: `python3.13 -m venv .venv && source .venv/bin/activate && pip install -r backend/requirements.txt && cp backend/.env.example backend/.env` (set `DATABASE_URL`, `JWT_SECRET`, `ADMIN_PASSWORD`); `cd backend && uvicorn app.main:app --reload --port 8000`.
3. Artifacts are committed; retrain only if needed: `PYTHONPATH=backend python ml/train.py && python ml/evaluate.py && python ml/export_artifacts.py`.
4. Frontend: `cd frontend && cp .env.example .env && npm ci && npm run dev` -> http://localhost:5173.
5. Tests: `cd backend && pytest -q`; `PYTHONPATH=backend pytest ml/tests -q`; `cd frontend && npm test`; with the backend running: `python scripts/e2e_smoke.py`.
