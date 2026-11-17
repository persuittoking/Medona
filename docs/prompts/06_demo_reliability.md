# Task 06 — Make the demo reliable (Gemini speed/503s + SLA demo setting)

Read CLAUDE.md first. Plan, then do each part, test, commit, and push (the remote is already set).
Never print or commit secret values.

## Part A — Finish the escalation fix that was skipped earlier
config.py still has `return 2 if self.demo_mode else ...`, so in DEMO_MODE every red alert escalates
after 2 minutes — that would happen in the middle of our pitch.
1. Add DEMO_SLA_RED_MINUTES (default 10) to config, .env and .env.example; use it in DEMO_MODE instead of
   the hard-coded 2.
2. Add an admin/specialist-only endpoint + a small button on the alert row:
   "Demo: SLA muddatini hozir tugatish" — sets that alert's sla_due_at to now, so the next scheduler run
   (≤30 s) escalates it. Only available when DEMO_MODE=true. Write it to the audit log. Add a test.

## Part B — Gemini: choose a fast, reliable model
Google is returning many 503 "high demand" errors and gemini-3.8-flash takes ~15 s per summary.
1. List the models this key can use. For each "flash" / "flash-lite" text model (max 5 candidates),
   make 3 real summary calls with the DEMO1 payload. Measure: success rate, average latency, whether the JSON
   validated, and whether the Uzbek text reads naturally. Also try the lowest thinking/reasoning setting
   the SDK allows for that model.
2. Print a small table (model | ok/3 | avg seconds | JSON valid | Uzbek quality note). Never print the key.
3. Set GEMINI_MODEL in backend/.env to the best model (3/3 success, fastest, good Uzbek), and add
   GEMINI_FALLBACK_MODEL (the second best). Update .env.example with the model names (not the key).

## Part C — Never make the user wait for the AI summary
1. Call order: primary model (structured) → on 503/504/timeout, GEMINI_FALLBACK_MODEL (structured) →
   plain-JSON retry → template "Shablon". Keep the total time within LLM_TIMEOUT_S. Record each attempt
   in the health status.
2. Generate the summary IN THE BACKGROUND right after a visit is saved (FastAPI BackgroundTasks or the
   scheduler), cached per risk assessment. The patient card shows "AI xulosa tayyorlanmoqda…" and polls
   every 3 s until it's ready (max 60 s), then shows it. By the time the specialist opens the card after the
   alert, the summary should already be there.
3. Pre-warm: on backend start (only when a key is present), generate summaries for the DEMO1–DEMO4
   patients in the background, spaced ~2 s apart, so the demo cards are instant.
4. Tests with mocked clients: primary 503 → fallback model succeeds; both fail → plain retry; all fail →
   Shablon; background generation stores the cached result.

## Part D — Check, commit, push
1. Run ruff, all backend tests, frontend typecheck/lint/build.
2. Run the demo flow once: DEMO1 → new visit 152/98, protein +2, severe headache → RED → log in as
   specialist → open the card: the AI summary should show "AI (Gemini)" (or the honest "Shablon" if Google
   is down) without a long wait. Then reset the demo data (DEMO1 yellow again).
3. Commit and `git push`. Print the ✅/❌ checklist and the model table from Part B.
