# PHASE 5 (A-G5) - LLM explanations, fallbacks and guardrails (Member 1)

Built on `proofhire_phase4.zip`. Model, artifacts, evidence engine, checklist, entities, schemas, router and every
teammate file are preserved. Contract details: `ml/AI_ML_INTEGRATION_CONTRACT.md` ("LLM contract (A-G5)").

## Verification of Phases 1-4 (done before building)
* Re-read the Phase 4 code and reports; `py_compile` of every file OK; `model.joblib` sha256 still equals
  `model_meta.json` (`a3f4855c...`); no change to features, model_store, evaluation/training code, schemas or data JSONs.
* Re-ran the Phase 1-4 `ml/tests` in this sandbox (Python 3.12, scikit-learn 1.8, **no pytest / pydantic / httpx /
  FastAPI and no network**) using verification-only stand-ins for pytest and pydantic (not shipped): 303 passed and 38
  skipped (the skips are the tests that need the committed scikit-learn 1.7.2 artifact). With the scikit-learn version
  gate bypassed for verification only (sklearn 1.8 unpickling the 1.7.2 model) those 38 also ran: 339 of 340 passed;
  the one failure was a gap in my pydantic stand-in (`model_fields`), not a repo problem.
* Nothing in Phases 1-4 needed fixing. Not re-verifiable here: `backend/tests` (needs FastAPI), the Phase 4 claim of
  "364 passed" on Python 3.13 / scikit-learn 1.7.2, and the metrics. Please re-run on the pinned venv.

## Files
Added: `backend/app/ml/llm_client.py`, `ml/tests/test_llm_client.py`, `ml/tests/test_template_explainer.py`,
`ml/tests/test_llm_pipeline.py`, `backend/.env.llm.example` (no secrets), this report.
Modified: `backend/app/ml/template_explainer.py` (rewritten, see below), `backend/app/ml/pipeline.py` (LLM integration),
`ml/tests/conftest.py` (autouse fixture: every test starts with all `LLM_*` variables removed),
`ml/tests/test_pipeline_explainable.py` (updated where it asserted Phase 4 interim behaviour: template signature, the
fixed concern texts, and the cache test that cached a template under the LLM-enabled key),
`ml/AI_ML_INTEGRATION_CONTRACT.md`. Untouched: everything else (including `routers/ml.py`, which already called
`pipeline.llm_circuit_open()` and `assess_listing(with_llm=True)` and needed no change).

## What was built
1. **Template explainer** `build_template_explanation(risk_level, evidence, checklist_hints=None)`: concerns are the
   evidence label plus the exact snippet; one pattern-level concern cites model evidence at medium/high; `what_to_verify`
   is the supplied checklist hints (one fixed generic sentence only when none are supplied); cautious wording; no network.
2. **LLM client** `generate_explanation(risk_level, evidence, checklist_hints) -> (Explanation, LlmMeta)`, never raises.
   OpenAI-compatible `POST {LLM_BASE_URL}/chat/completions` (Bearer key, `response_format json_object`), A10 system
   prompt verbatim (+ one security sentence), A10 user message JSON (no score in it), env-only configuration.
3. **Sequence:** disabled / no key / cache hit / breaker open / limiter refuses -> as documented; then primary; on timeout,
   HTTP 429, HTTP 5xx or unusable JSON ONE fallback call if configured; else template. At most two HTTP calls, each capped
   by `LLM_TIMEOUT_SECONDS`; no retry loop.
4. **Validation, cache, limiter, breaker** as in the contract file (cache 256 / 24 h, limiter `LLM_RPM_LIMIT` per minute,
   breaker 3 failures -> 120 s -> one recovery attempt). `llm_meta` distinguishes LLM answers from template fallbacks.
5. **Pipeline:** `with_llm` now takes effect (`with_llm AND LLM_ENABLED=true`). Score, level, evidence, checklist and
   entities are computed first and are identical whatever the LLM does (tested). A failed LLM attempt is not cached.

## Tests actually run (stand-ins, see above; no real API was called)
* New: 112 LLM-client tests (+1 skipped: the httpx `MockTransport` test), 13 template tests, 10 pipeline-integration tests.
* Whole `ml/tests` with the version gate bypassed: **475 passed, 1 failed (stand-in gap above), 2 skipped** (Member 4's
  real checklist library is absent; the httpx test needs `httpx`). As-is in this sandbox: **428 passed, 0 failed, 50 skipped**.
* Mutation check: 12 deliberate breaks (fallback eligibility, breaker threshold, id validation, cache TTL, limiter,
  summary cap, health flag, response_format, LLM cache write, caching of failed attempts, reload clearing the LLM cache,
  `with_llm` ignored) - all 12 were detected by the new tests.
* NOT run: any live Groq / OpenRouter call (no credentials or network); the real `pytest` / `pydantic` / `httpx`;
  `backend/tests`; a live server. The real HTTP function `_post_json` is covered only by a test that needs `httpx`
  (skipped here) - run `PYTHONPATH=backend pytest ml/tests -q` on the pinned venv.

## Decisions and open points for you
1. `LLM_ENABLED` must be the literal `true` (default off); a key alone does not enable it, so no test or dev shell can reach
   a provider by accident. `render.yaml` already sets it to `true`.
2. Fallback only for the four documented conditions. A refused connection (`network_error`) or an HTTP 400/401/403/404
   goes straight to the template; "no valid concern" is not retried on the fallback. One constant (`FALLBACK_ELIGIBLE`)
   changes this if you disagree.
3. Cache key is a superset of the guidebook's (adds ids, labels, hints) because a cached answer cites ids.
4. An answer with zero concerns is accepted only when the assessment had no risk-increasing evidence; otherwise template.
5. The wording filters are heuristics (scam/fraud/fake statements, legal claims, vouching, score, wrong level, links); they
   can reject a harmless sentence, in which case the template is used. They cannot prove the model's statements are true -
   the system prompt and the id check limit, not eliminate, invention.
6. `openai/gpt-oss-120b` is a reasoning model: reasoning tokens may eat into `LLM_MAX_TOKENS=450`. If live answers are empty
   or cut off (`llm_meta.error_code = bad_json`), raise `LLM_MAX_TOKENS` - verify on the day with the real key.
7. For Member 3: `llm_meta` is now meaningful. LLM answer: `groq`/`openrouter`, success true. Template fallback after the LLM
   was wanted: `template`, success false, `error_code` set. Deliberate template: `template`, success true. A cached answer has
   `latency_ms` 0. `httpx` must be in `requirements-render.txt` (it is in the guidebook list).

## Environment / setup
Variables: see `backend/.env.llm.example` (merge into `backend/.env`; set the key in the Render dashboard). No new Python
dependency beyond `httpx` (already in the guidebook). Run: `PYTHONPATH=backend pytest ml/tests backend/tests -q` on
Python 3.13 / scikit-learn 1.7.2.

## Next phase (A-G6) prerequisites
Member 4's `handwritten_eval.csv` and `checklist_library.json`, `scripts/export_feedback.py`, a Groq key for one live
smoke test of the explanation path (not yet done), and the open threshold decision from the Phase 3 report.
