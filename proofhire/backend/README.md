# ProofHire backend (Phase 6: foundation, database, authentication, assessments, checklist, compare, reports, admin moderation and dashboard)

FastAPI + SQLAlchemy 2.0 + MySQL 8.4. This phase has the app skeleton, configuration, the eight database
tables, the standard error format, `GET /api/v1/health`, and **authentication**: register, login, who-am-I,
admin bootstrap and role-based access, the **assessment endpoints** (Phase 3: create, list, read, delete) and
(Phase 4) **checklist updates** and **assessment comparison**, (Phase 5) **community reports and admin moderation** and (Phase 6) the **dashboard** endpoints. Hardening (rate limit, lockfile, deployment) comes in a later phase. ML code belongs to the AI/ML teammate:
the backend only calls their `assess_listing()` (see `docs/ML_INTEGRATION.md`; **integration is pending**).

## What is where

```
backend/
  app/main.py            app factory, startup (lifespan), CORS, /api/v1 routing
  app/core/config.py     settings from environment variables and backend/.env
  app/core/errors.py     Section 5.5 error format and handlers
  app/core/security.py   bcrypt hashing, JWT (HS256), owner-token helpers
  app/core/deps.py       get_db, get_current_user, get_optional_user, require_admin, verify_internal_key
  app/db/base.py         SQLAlchemy base
  app/db/session.py      engine, sessions, check_db()
  app/db/models.py       the eight Section 6 tables
  app/db/init_db.py      creates the tables (Base.metadata.create_all, no Alembic)
  app/db/seed.py         creates the first admin from ADMIN_EMAIL / ADMIN_PASSWORD
  app/routers/health.py  GET /api/v1/health
  app/routers/auth.py    POST /auth/register, POST /auth/login, GET /auth/me
  app/routers/assessments.py   POST/GET /assessments, GET/DELETE /assessments/{id}, PATCH checklist, POST compare
  app/services/ml_gateway.py   the ONLY code that touches the ML package (503 while it is missing)
  app/services/assessment_service.py   scoring call, one-transaction save, access rules, list, delete
  app/services/connection_service.py   repeat-pattern connections and masking (B6)
  app/services/compare_service.py      POST /assessments/compare: one row per signal, lower risk wins
  app/routers/reports.py       POST /reports, GET /reports/mine
  app/routers/admin.py         GET /admin/reports, PATCH /admin/reports/{id}  (administrators only)
  app/services/report_service.py   create report, my reports, moderation queue, approve/reject
  app/schemas/report.py        report request/response models (B4)
  app/routers/dashboard.py     GET /dashboard/summary, /dashboard/trends, /dashboard/model-metrics (all public)
  app/services/dashboard_service.py   dashboard SQL, 30 s / 60 s caches, metrics.json reader
  app/schemas/dashboard.py     dashboard response models
  app/schemas/assessment.py    ListingInput (5.2), AssessmentResult (5.3), list models
  app/schemas/           health and auth request/response models
  tests/                 pytest suite (needs no MySQL: uses in-memory SQLite)
  .env.example           copy to .env
```

## 1. Prerequisites
Python **3.13.16**, MySQL **8.4** (local install or Docker), and PowerShell on Windows.

## 2. Create the database (once)
Docker shortcut:
```powershell
docker run --name proofhire-mysql -e MYSQL_ROOT_PASSWORD=root -e MYSQL_DATABASE=proofhire -e MYSQL_USER=proofhire -e MYSQL_PASSWORD=proofhire -p 3306:3306 -d mysql:8.4
```
Or run this in `mysql -u root -p`:
```sql
CREATE DATABASE proofhire CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER 'proofhire'@'localhost' IDENTIFIED BY 'proofhire';
GRANT ALL PRIVILEGES ON proofhire.* TO 'proofhire'@'localhost';
FLUSH PRIVILEGES;
```

## 3. Install and configure (from the repo root)
```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend\requirements.txt
cd backend
copy .env.example .env
```
`backend/.env` is ignored by git. Edit `DATABASE_URL` if your user, password or port differ.

## 4. Configure authentication (required before register/login work)
Edit `backend/.env` (never commit it):

1. **JWT secret.** Generate your own and paste it after `JWT_SECRET=`:
   ```powershell
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```
   Without it, `/auth/register` and `/auth/login` answer `500 internal_error` and the log says why.
2. **First administrator (optional).** Set `ADMIN_EMAIL` and a strong `ADMIN_PASSWORD` (8-72 bytes) of your own.
   At startup, if no admin exists yet, one is created. Leave them empty to create none. An existing regular
   account with that email is **never** promoted. Public registration can only create regular users.
3. `BCRYPT_ROUNDS` is 12 by default (10 if login feels slow on the Render free CPU).

Nothing secret is stored in the code or in this repository: passwords are stored only as bcrypt hashes.

## 5. Run the tests (no MySQL needed)
```powershell
cd backend
pytest -q
```
The tests set their own fake JWT secret and a low bcrypt cost, so your `.env` is not needed for them.

## 6. Create the tables and start the server
```powershell
cd backend
$env:PYTHONPATH = "."
python -m app.db.init_db        # expect: OK: 8 tables present: ...
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
- Swagger UI: http://localhost:8000/docs
- Health: http://localhost:8000/api/v1/health

## 7. Try the authentication endpoints
With the server running (examples use PowerShell's `curl.exe`; Swagger UI at /docs is easier):
```powershell
# Register (201): returns {access_token, token_type, user}
curl.exe -s -X POST http://localhost:8000/api/v1/auth/register -H "Content-Type: application/json" -d "{\"email\":\"you@example.com\",\"password\":\"choose-a-password\",\"display_name\":\"You\"}"
# Log in (200): same response shape
curl.exe -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d "{\"email\":\"you@example.com\",\"password\":\"choose-a-password\"}"
# Who am I (200): paste the access_token
curl.exe -s http://localhost:8000/api/v1/auth/me -H "Authorization: Bearer PASTE_TOKEN_HERE"
```
In Swagger UI click **Authorize**, paste the token, and the lock icons turn on.

| Endpoint | Success | Errors |
|---|---|---|
| `POST /auth/register` `{email, password (8-72), display_name (1-100)}` | 201 | 409 duplicate email, 422 validation |
| `POST /auth/login` `{email, password}` | 200 | 401 (same message for unknown email and wrong password) |
| `GET /auth/me` | 200 `{id, email, display_name, role}` | 401 missing/invalid/expired token |

Security notes: tokens are HS256 JWTs that expire after `JWT_EXPIRE_MINUTES`; the server always re-reads the
user's role and active flag from the database, so demoting or disabling an account takes effect immediately.
Passwords are limited to 72 **bytes** (bcrypt's limit), so a very long password with accented characters can
be rejected earlier than 72 characters.

The health route is `/api/v1/health` (inside the prefix), as in guidebook Section 5.4 and 12.5.
`status` is `ok` only when the database answers **and** the ML model is loaded. Until the ML teammate's
`app.ml.pipeline` exists you will see `status: degraded`, `db: true`, `model_loaded: false`. That is expected.

## 8. Assessments (Phase 3)

| Endpoint | Who | Success | Errors |
|---|---|---|---|
| `POST /assessments` `ListingInput` | anyone (logged in or anonymous) | 201 `AssessmentResult` (+ `owner_token` for anonymous callers only) | 401 bad token, 422 validation, **503 `model_unavailable`** (ML missing or not loaded), 500 |
| `GET /assessments?page=1&limit=20&risk_level=` | login required | 200 `{items, total, page, limit}`, own assessments only, newest first | 401, 422 |
| `GET /assessments/{id}` | anyone who knows the id | 200 `AssessmentResult`; contact details only for the owner | 404 |
| `DELETE /assessments/{id}` | owner (JWT user, or `X-Owner-Token`) | 204 | 403 not owner, 404 |

**Important: the ML teammate's files are not in this project yet.** Until `app/ml/pipeline.py` and
`app/schemas/ml_schemas.py` are added, `POST /assessments` correctly answers
`503 {"error": {"code": "model_unavailable", ...}}`. That is the designed behaviour, not a bug. The backend never
invents a score. The automated tests use test-only fakes (`tests/ml_fakes.py`).

### Check it in Swagger UI (http://localhost:8000/docs)
1. **Without the ML files:** open `POST /api/v1/assessments`, *Try it out*, use the example body, *Execute*.
   Expect **503** with `code: model_unavailable`. Confirm in MySQL that nothing was saved
   (`SELECT COUNT(*) FROM listings;` is 0).
2. **Validation:** send `"title": "ab"` and expect **422** with a `fields` entry for `title`.
3. **After the ML files are added** (restart the server; `GET /health` should show `model_loaded: true`):
   - Anonymous `POST /assessments` returns **201** including `owner_token`. Copy it now: it is shown only once.
   - `GET /assessments/{id}` with no header shows `contact_email` masked (`h***@...`). Add header
     `X-Owner-Token: <token>` (Swagger's *Try it out* has the field) and it shows the full value.
   - Click **Authorize**, paste a token from `/auth/register`, run `POST` again: the 201 has **no** `owner_token`.
   - `GET /assessments` (needs Authorize) lists only your assessments; try `limit=2&page=2` and `risk_level=high`.
   - `DELETE /assessments/{id}` as the owner returns **204**; the same call as someone else returns **403**.

### Tests
```powershell
cd backend
pytest -q
```
Needs no MySQL and no ML files. See `BUILD_ORDER.txt` for the honest test status of this delivery.

## 9. Checklist, compare and connections (Phase 4)

| Endpoint | Who | Success | Errors |
|---|---|---|---|
| `PATCH /assessments/{id}/checklist/{item_id}` `{"done": true}` | owner: the logged-in user, or an anonymous owner with header `X-Owner-Token` | 200 `{id, done}` | 401 bad token, 403 not owner, 404 unknown assessment or item, 422 |
| `POST /assessments/compare` `{"assessment_id_a": 1, "assessment_id_b": 2}` | anyone | 200 `{a, b, rows:[{signal, a, b, better}]}` | 400 same id twice, 404 missing, 422 |

**Checklist PATCH.** The check order is: unknown assessment (404), then not the owner (403), then item not found or
belonging to a different assessment (404), so a stranger cannot probe which item ids exist. `done` must be a real
`true` or `false` (`"yes"` or `1` give 422). The server sets `done_at`; sending the same value twice is harmless.
The raw owner token is only ever returned when the anonymous assessment is created, never by PATCH or GET.

**Compare.** One row per signal, always in this order: `risk_score`, `risk_level`, `upfront_fee_amount`,
`salary_monthly`, `email_type` (`company`, `free` or `none`), `website_present`, `interview_mode`,
`application_channel`, `observed_risk_signals`, `approved_reports`, `connections_count`. `better` is `a`, `b` or
`tie`, and **lower risk wins**. Pay (`salary_monthly`) is always `tie` because the backend has no honest way to rank
it. Contact e-mail and phone are never returned, only the e-mail *type*. Scores and levels are the stored ML result;
the backend computes nothing about risk.

**Connections** (shown inside every assessment): another assessment is a match when it has the **same
`signal_type` and `signal_value`**; the assessment itself never counts. `times_seen` = others + 1, `high_risk_count`
= how many of the others are high risk. Emails show as `h***@gmail.com`, phones as `******1234`; domains and company
names are shown as they are. Seeded demo rows are ignored. The lookup filters on `(signal_type, signal_value)`, the
columns of the `idx_signal` index.

### Try it in Swagger UI (needs the ML files, or the 503 appears)
1. Create two assessments (`POST /assessments`) and note both `assessment_id` values and the `owner_token` of an
   anonymous one.
2. `PATCH /assessments/{id}/checklist/{item_id}` with body `{"done": true}` and header `X-Owner-Token: <token>`
   (or **Authorize** as the owner). Expect 200 `{id, done}`. Without the token expect **403**.
3. `POST /assessments/compare` with the two ids. Same id twice gives **400**; an unknown id gives **404**.
4. Create a second listing with the same company e-mail domain: both assessments now show a connection.

## 10. Reports and admin moderation (Phase 5)

| Endpoint | Who | Success | Errors |
|---|---|---|---|
| `POST /reports` `{assessment_id, report_type, description (10-1000)}` | anyone (anonymous or logged in) | 201 `{id, status: "pending"}` | 401 bad token, 404 unknown assessment, 409 duplicate, 422 validation |
| `GET /reports/mine` | login required | 200 `[{id, assessment_id, report_type, description, status, moderator_note, created_at}]` | 401 |
| `GET /admin/reports?status=pending&page=1&limit=20` | **administrator only** | 200 `{items:[{id, assessment_id, listing_title, company_name, report_type, description, status, created_at}], total}` | 401 no/bad token, 403 not an admin, 422 |
| `PATCH /admin/reports/{id}` `{status: "approved"\|"rejected", moderator_note (max 500)}` | **administrator only** | 200 the updated report (same fields as `/reports/mine`) | 401, 403, 404 unknown id, 409 already reviewed, 422 |

`report_type` is one of `advance_fee`, `impersonation`, `personal_data_request`, `fake_company`, `harassment`, `other`.
Status is `pending` (every new report), `approved` or `rejected`. Nobody can create a report with another status:
extra fields in the request body are ignored.

**Who reports.** Logged-in callers are identified by their user id; anonymous callers by `sha256(IP + User-Agent)`
(the IP is the first value of `X-Forwarded-For` when present, as on Render). The same reporter cannot report the same
assessment for the same `report_type` twice (409); a different type, a different assessment or a different reporter is fine.
Anonymous reports are stored but are not linked to an account, so they never appear in `/reports/mine`.
Descriptions are trimmed first, then length-checked (10-1000 characters).

**Moderation.** Only a user whose role in the **database** is `admin` can use `/admin/*` (a token that merely claims
`admin` gets 403). Create the first admin with `ADMIN_EMAIL` / `ADMIN_PASSWORD` (section 4). A decision records the moderator,
the time and the optional note, and cannot be changed afterwards (409). An **approved** report raises `report_count_approved`
on that assessment right away; a rejected one does not.

### Try it in Swagger UI (http://localhost:8000/docs)
1. Create an assessment (needs the ML files, see section 8) and note its `assessment_id`.
2. `POST /reports` with `{"assessment_id": <id>, "report_type": "advance_fee", "description": "They asked for a fee on WhatsApp."}`: expect **201**, `status: pending`. Repeat it: expect **409**. Use a 9-character description: expect **422**.
3. Click **Authorize** with a normal user's token: `GET /reports/mine` works, `GET /admin/reports` gives **403**.
4. Authorize with the admin's token (from `/auth/login` with `ADMIN_EMAIL`): `GET /admin/reports` lists the pending report; `PATCH /admin/reports/{id}` with `{"status": "approved", "moderator_note": "Specific payment request."}` gives **200**. Repeat the PATCH: **409**.
5. `GET /assessments/{id}`: `report_count_approved` is now 1.

## 11. Dashboard and model metrics (Phase 6)

All three endpoints are **public** (no login). They never write anything.

| Endpoint | Query | Success | Errors |
|---|---|---|---|
| `GET /dashboard/summary` | `include_demo` (bool, default `false`) | 200 `{total_assessments, by_level{low,medium,high}, avg_risk_score, top_evidence[{code,label,count}], reports{total,pending,approved,rejected}, connections_found, llm{calls,success_rate,avg_latency_ms,template_fallbacks}, data_scope}` | 422 bad query value |
| `GET /dashboard/trends` | `days` (1-60, default 14), `include_demo` (default `false`) | 200 `[{date, count, high, medium, low}]`, oldest first, one entry per day, zero-filled | 422 |
| `GET /dashboard/model-metrics` | none | 200 the contents of `metrics.json` plus `model_version`, header `Cache-Control: public, max-age=300` | **503 `model_unavailable`** if the file is missing or invalid |

**Demo data (decision D9).** Rows seeded by `scripts/seed_demo.py` have `listings.is_synthetic_demo = 1`. By default every
number leaves them out, together with their evidence, signals and reports. `include_demo=true` adds them and
`data_scope` becomes `"including_demo"` (it is `"real_only"` otherwise), so the page can always say which one it shows.

**How the numbers are calculated** (from the stored rows, with SQL):
- `total_assessments`, `by_level`: number of assessments, and per `risk_level`. `avg_risk_score`: mean stored `risk_score`, 4 decimals.
- `top_evidence`: the 8 most frequent `(code, label)` pairs in `evidence_items`, most frequent first (ties by code). A `MODEL_TERM` item
  has the term in its label, so each wording is its own entry.
- `reports`: reports on the counted assessments, by status.
- `connections_found`: the number of distinct `(signal_type, signal_value)` pairs that appear in **two or more different** assessments.
- `llm.calls`: rows in `llm_calls` whose provider is not `template` (the built-in template fallback is not an LLM call).
  `success_rate` = successful calls / calls (0 to 1). `avg_latency_ms` = mean latency of those calls.
  `template_fallbacks` = assessments whose explanation came from the template (`explanation_source = 'template'`).
- **No data means `null`, not 0:** with no assessments `avg_risk_score` is `null`; with no LLM calls `success_rate` and `avg_latency_ms` are `null`.
- `trends`: the last `days` calendar days **in UTC, ending today**, one entry per day even when it has no assessments.
  Example for `days=14` on 2026-10-12: 2026-09-29 ... 2026-10-12.
- Caches: summary 30 seconds, trends 60 seconds, each per parameter combination (so `include_demo` never mixes). A new assessment can take up to 30-60 s to show.

### `metrics.json` (written by the AI/ML teammate, only read here)
Location: **`backend/app/ml/artifacts/metrics.json`**, next to `model.joblib` and `model_meta.json` (guidebook A12). The backend never creates,
changes or recomputes it: Member 1's `export_artifacts.py` / `evaluate.py` produce it, it is committed to git and deployed with the app.
The file is read on every request (it is a few KB). `model_version` in the response comes from `model_meta.json` in the same folder
(`null` if that file is missing or unreadable, with a warning in the server log).

Expected structure (guidebook A11; extra keys are allowed and passed through):
```json
{
  "synthetic_test": {"precision": 0.0, "recall": 0.0, "f1": 0.0, "roc_auc": 0.0, "pr_auc": 0.0, "brier": 0.0,
                     "confusion": [[0, 0], [0, 0]]},
  "baselines": {"M0": {}, "M1": {}, "M2": {}, "M3": {}, "M4": {}},
  "pattern_holdout": {"recall": 0.0, "n": 0},
  "handwritten": {"precision": 0.0, "recall": 0.0, "n": 0},
  "cv": {"pr_auc_mean": 0.0, "pr_auc_std": 0.0},
  "limitations": ["..."]
}
```
(The zeros only show the types. Real values come from Member 1's evaluation.) The backend checks: the file is a JSON object under 1 MB with
no `NaN`/`Infinity`; `synthetic_test`, `baselines`, `pattern_holdout`, `handwritten`, `cv` are objects; `limitations` is a list of strings;
`synthetic_test` has the six numbers above and a 2x2 `confusion` of numbers.

**If the file is missing or does not match, the endpoint answers `503 model_unavailable`** with a message such as
`Model metrics are not available: metrics.json was not found` (or `... is not valid JSON`, `... is too large ...`,
`... does not have the expected structure (missing key(s): cv)`). It never returns placeholder or default numbers, and the error is not cached.
Until Member 1's artifacts are added to this project, `/dashboard/model-metrics` therefore answers 503. That is expected.

### Try it in Swagger UI
1. `GET /dashboard/summary`: on an empty database you see zeros and `null` averages. Create assessments, then wait 30 s (or restart) to see them.
2. After `python scripts/seed_demo.py` (Member 4), compare `include_demo=false` and `include_demo=true`: totals differ and `data_scope` changes.
3. `GET /dashboard/trends?days=7` returns 7 entries; `days=61` returns 422.
4. `GET /dashboard/model-metrics`: 503 until `backend/app/ml/artifacts/metrics.json` exists; 200 afterwards.

## Troubleshooting
| Symptom | Fix |
|---|---|
| `Invalid configuration ... DATABASE_URL` | `backend/.env` is missing or the URL is wrong (must start with `mysql+pymysql://`). |
| `MySQL error 2003` | MySQL/Docker is not running, or host/port is wrong. |
| `MySQL error 1045` | Wrong user or password in `DATABASE_URL`. |
| `MySQL error 1049` | The `proofhire` database does not exist yet (step 2). |
| `cryptography package is required` | `pip install cryptography` (already in requirements). |
| `POST /assessments` returns 503 | The ML package is missing or its model is not loaded (see `docs/ML_INTEGRATION.md`). |
| `/auth/login` or `/auth/register` returns 500 | `JWT_SECRET` is empty in `backend/.env` (step 4). |
| `ModuleNotFoundError: app` | Run commands from `backend/` and set `$env:PYTHONPATH = "."`. |

Error messages and logs never include passwords; the database password is masked as `***`.
If you change a model, `create_all` will not alter an existing table: drop the table (or the local database) and run `python -m app.db.init_db` again.
