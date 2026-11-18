# Task 14: Final polish before the demo (small, safe fixes + docs)

Read CLAUDE.md first. EXTEND, do not rewrite. Do NOT touch .env contents or commit *.db. Do NOT git push.

## Part A: Security hygiene
1. `PINFL_HASH_SECRET`: make `app/make_env.py` generate a separate random value, add it (empty) to `backend/.env.example`,
   and when DEMO_MODE is false refuse to start if it is empty or equal to JWT_SECRET. Keep the dev fallback only in DEMO_MODE.
   Existing demo DBs: changing the secret changes hashes, so backfill must recompute pinfl_hash for all rows (reuse backfill_pinfl_hashes
   with a "force" option) and a test must cover it.
2. In `visits.py`, check `resolve_external_pregnancy` / `resolve_external_newborn` callers: external entry by bare pregnancy_id,
   patient_code or child_code must be subject to the same hourly limit (30/h per user) and audit (hit and miss) as the
   PINFL lookup. Fix if not, with tests.
3. If JWT_SECRET equals the dev default and DEMO_MODE is false, refuse to start.

## Part B: Honest labels
1. `STANDARD_VISIT_WEEKS` in thresholds.py was not provided by a clinician: add a comment "DEMO calendar, to be replaced by the
   national schedule confirmed by an obstetrician" and show "demo jadval" next to it in the UI patient card.
2. Replace the stale README line saying the demo SLA is 2 minutes with the DEMO_SLA_RED_MINUTES wording.
3. Correct CLAUDE.md "Tech stack" to the real prototype (SQLite, send-only Telegram adapter, no Docker/Alembic/aiogram yet) and add
   a "Production plan" line (PostgreSQL, Docker, bot service, in-country hosting).
4. MODEL_CARD.md and README must quote the metrics from backend/ml/artifacts/metrics.json (do not hand-copy numbers).

## Part C: Docs for the pitch (English, short)
1. docs/CODE_TOUR.md: one page per area (backend, risk, llm, security, services, frontend, tests): what each file is for.
2. docs/QA_PREP.md: 25 likely mentor questions with 2-3 sentence honest answers: DMED vs OnaRadar, who pays, offline use,
   fake "accept" clicks, unreachable patients, 12 mandatory visits, privacy and data location (Law ZRU-547, localization amended
   March 2026), synthetic data, model limits (ROC-AUC from metrics.json), clinician validation, Gemini data handling.
3. docs/BUSINESS_MODEL.md: payer logic (Ministry/regions/donors, doctor is the user not the customer), pricing hypotheses,
   break-even table (clearly labelled as assumptions).

## Part D: Demo readiness
1. Add `check_demo.ps1` that: verifies backend/.env exists and has non-empty JWT_SECRET, FERNET_KEY (never print values),
   reports whether GEMINI_API_KEY is set, runs `GET /api/health` and `GET /api/llm/health` (admin login), confirms the
   DEMO1-DEMO4 summaries are cached, and prints PASS/FAIL per line.
2. Make reset_demo.bat print a reminder to restart the backend afterwards.
3. Run the full DEMO_SCRIPT flow once in the browser (nurse red-only map, DEMO1 to red, specialist alert + 3 bullets, escalation button,
   children switch, external entry, proof-of-care scene if task 12 is merged), then reset the demo data.

## Finish
ruff check backend, pytest -q, frontend typecheck, lint, build. ONE local commit "Final polish: security hygiene, honest labels, docs,
demo check", do NOT push. Print a checklist with the result of each numbered item.
