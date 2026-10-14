# ML integration status (Backend <-> Member 1)

**Status: PENDING.** The ML package has not been delivered. The backend is finished up to the boundary and
answers `503 model_unavailable` until the files below exist. Nothing in the backend scores a listing.

## The boundary: `backend/app/services/ml_gateway.py` (the only file that touches ML code)

Taken from guidebook A2, C2 and B4:

| Backend uses | Provided by | Notes |
|---|---|---|
| `app.schemas.ml_schemas.ListingInput` | Member 1 | the backend validates the request itself (Section 5.2), then converts with `ListingInput.model_validate(listing.model_dump())` |
| `app.ml.pipeline.assess_listing(listing, with_llm=True)` | Member 1 | called once per POST, inside the route's worker thread |
| `app.ml.pipeline.model_status()` | Member 1 | if it returns `loaded: false`, the backend answers 503 and does not call `assess_listing` |
| `app.ml.entities.FREE_MAIL_DOMAINS` | Member 1 | optional; if absent the six domains named in Section 6 are used |

## What the backend expects back (documented shape, `MlOutput` in `ml_gateway.py`)
`risk_score` (0..1), `risk_level` (`low|medium|high`), `thresholds {low, high}`, `model_version`,
`evidence[] {id, code, label, type, direction, severity 1..3, snippet|null, weight|null}`,
`explanation {source llm|template, summary, key_concerns[{text, evidence_ids}], what_to_verify[]}`,
`checklist[] {code, text, priority}` (no ids), `entities[] {type, value}`, `llm_meta {provider, model, latency_ms, success, error_code}`.
Extra fields are ignored. A different shape is an integration bug: logged (field paths only) and answered with a generic 500.

## Open questions for Member 1 (answer before integration)
1. Is `MlResult.model_dump()` exactly the shape above? (A2 lists the fields in prose; names follow Section 5.3.)
2. Which exception, if any, does `assess_listing` raise when the model is not loaded? (Today: any exception becomes a generic 500; only `model_status()` or a missing module gives 503.)
3. Is `llm_meta` always present? (If absent, no `llm_calls` row is written.)
4. Do `entities` already exclude free-mail domains and normalise phones (A9)? (The backend also skips free-mail domains defensively.)

## When the files arrive
1. Copy `app/ml/`, `app/schemas/ml_schemas.py` and `app/data/*` into `backend/`; install any new requirements.
2. `pytest -q` (the gateway tests use fakes installed in `sys.modules`, so they still pass with the real package present).
3. Start the app: `GET /api/v1/health` should show `model_loaded: true`; then try `POST /api/v1/assessments` in Swagger.
4. Compare `MlResult` with `MlOutput`; record any difference in `docs/CONTRACT_CHANGELOG.md`.

## Dashboard dependency (Phase 6)
`GET /api/v1/dashboard/model-metrics` reads two files from `backend/app/ml/artifacts/` and does not import any ML code:
- `metrics.json`, in exactly the structure of guidebook A11 `/ml/metrics` (see backend/README.md section 11 for the checks);
- `model_meta.json`, only for its `model_version`.
Until these exist the endpoint answers 503 `model_unavailable`. Open question for Member 1: B4 mentions `get_metrics()`; if it should be used
instead of reading the file, tell the backend its module and return shape.

## Review status (2026-10-12, "ML-ready" review of the Phase 6 ZIP)
Result of reviewing the Phase 6 project for ML readiness. No application code was changed: the boundary, the
validation, the error handling and the metrics reader described above already existed and match this document.

**Verified by reading the code (not by running the real ML module, which does not exist yet):**
- `ml_gateway.py` is the only file that imports `app.ml.pipeline` / `app.schemas.ml_schemas`; imports are lazy, so the app starts without them.
- Missing package, missing `assess_listing`, missing `ListingInput`, `loaded: false` or a failing `model_status()` give 503 `model_unavailable` before any database write.
- An exception from `assess_listing`, or an answer that does not fit `MlOutput`, gives a generic 500 `internal_error` (field paths only are logged).
- `assessment_service.create_assessment` stores the validated result in one transaction and rebuilds the response from the stored rows.
- `GET /dashboard/model-metrics` reads `backend/app/ml/artifacts/metrics.json` (+ `model_version` from `model_meta.json`); a missing, unreadable, oversized or malformed file gives 503 and no number is ever substituted.
- The only ML stand-ins are in `tests/ml_fakes.py` (installed into `sys.modules` by tests); nothing in `app/` fakes a model.

**Not verified:**
- The test suite was NOT run in this review (the review sandbox cannot install FastAPI, SQLAlchemy, pytest and the other requirements). Phase 6 tests (`tests/test_dashboard.py`) have never been run by anyone, according to `BUILD_ORDER.txt`. Run `python -m pytest -q` in `backend/`.
- The guidebook itself was not part of the ZIP, so the interface above is as recorded in the existing code comments and docs (A2, B4, C2, A11, A12), not re-checked against the guidebook text.
- Real ML integration: pending until Member 1 delivers `app/ml/*`, `app/schemas/ml_schemas.py`, and the artifacts. The open questions above still need Member 1's answers.
