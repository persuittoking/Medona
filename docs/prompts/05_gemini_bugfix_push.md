# Task 05 — Switch AI to Gemini, fix remaining bugs, push to the new GitHub repo

Read CLAUDE.md first. Work in plan mode, then do each part in order, testing as you go.
NEVER print, log, echo or commit any secret value (API keys, JWT_SECRET, FERNET_KEY). When you need to
check a secret, check only that it exists and how long it is.

## Part A — Switch the LLM provider from Anthropic to Gemini

backend/.env already contains (values set by the team, don't print them):
  LLM_PROVIDER=gemini
  GEMINI_API_KEY=...
  GEMINI_MODEL=...
The file has Windows line endings (CRLF): make sure the settings loader strips "\r" and spaces
from the values, or the key will be invalid.

1. config.py: add llm_provider, gemini_api_key, gemini_model, and remove anthropic_api_key / llm_model.
   Update backend/.env.example to match, with EMPTY values for every secret
   (GEMINI_API_KEY must stay empty in .env.example — it is committed to git).
   Remove the old ANTHROPIC_API_KEY and LLM_MODEL lines from backend/.env (edit the file in place;
   don't print it).
2. backend/app/llm/: replace the Anthropic call with Gemini using the official `google-genai` SDK
   (`pip install google-genai`, `from google import genai`, `from google.genai import types`).
   Check the installed SDK version and use its real API:
   - client = genai.Client(api_key=settings.gemini_api_key), with a request timeout of ~15 s
     (types.HttpOptions), and no automatic retries beyond ours.
   - generate_content(model=settings.gemini_model, contents=<the de-identified JSON payload>,
     config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT,
     response_mime_type="application/json", response_schema=<LlmOutput or its JSON schema>,
     temperature=0.2)).
   - Validate the result with the LlmOutput Pydantic model. Keep the action-catalog validation
     (unknown action codes are dropped) and the fixed Uzbek disclaimer.
   - If the structured call fails, retry ONCE with a plain JSON-only prompt (no response_schema),
     then validate it. If that also fails → the template fallback (tag "Shablon").
   - Success tag in the UI: "AI (Gemini)". Change every "AI (Claude)" text in the frontend and docs.
   - Keep the PII guarantee: only the de-identified allow-list payload is sent. Keep/adjust the tests.
   - /api/llm/health: show provider, whether a key is present, the model name, last call ok/failed,
     and the last error (type + message, max 300 chars, never the key).
3. Remove the `anthropic` package from requirements.txt and add `google-genai`. Install it in the venv.
4. LIVE CHECK: call the summary for QQR-NUK-DEMO1 once with the real key. Print ONLY the tag
   ("AI (Gemini)" or "Shablon"), the model name, and the first 200 characters of summary_uz.
   If the API rejects the key, say so clearly (the key may have been copied wrongly — the team will
   re-copy it from Google AI Studio). Don't try to work around a rejected key.
5. Docs: update README, CLAUDE.md, docs/PRIVACY_AND_LEGAL.md (if it exists) and the About page:
   the provider is Google Gemini; only de-identified clinical values are sent; note that for real
   patient data a paid Gemini API tier should be used, because free-tier prompts may be used by Google
   to improve its products (check Google's current terms and phrase this carefully).

## Part B — Bug sweep

1. Backend lint: install ruff in the venv (add a requirements-dev.txt with ruff + pytest),
   run `ruff check --fix`, and fix the remaining warnings that matter (unused imports, undefined names,
   bare excepts other than our documented fallback).
2. Frontend: add a `typecheck` script (`tsc --noEmit`) and an ESLint setup with a `lint` script.
   Run both and fix the errors. `npm run build` must pass.
3. Run all backend tests; fix the failures.
4. Click through the full demo flow in the browser (nurse → DEMO1 → new visit 152/98, protein +2,
   severe headache → RED → specialist sees the alert → acknowledge → AI summary tag) and fix anything broken.
   Also check: Chilonzor nurse can't see Nukus patients; region.admin sees counts only.
5. Clean-up: the start/run .bat scripts still work in PowerShell (also add equivalent .ps1 scripts:
   start_all.ps1, run_backend.ps1, run_frontend.ps1). README "how to run" works on a clean clone.

## Part C — Prepare and push to the NEW GitHub repository

1. Safety checks (report the results, never the values):
   - `git ls-files` must NOT contain backend/.env, any *.db file, backend/backup_before_gemini.env,
     node_modules or .venv.
   - Search the whole git history for secrets: patterns `AIza`, `sk-ant-`, and the exact current values
     of GEMINI_API_KEY, JWT_SECRET and FERNET_KEY (compare inside a script without printing them).
     If anything is found, STOP and tell me — don't push.
   - backend/.env.example contains no real secret values.
2. Commit everything with a clear message.
3. ASK ME for the new repository URL (I am creating it on GitHub). When I give it:
   - `git remote remove origin` if one exists, then `git remote add origin <URL>`
   - `git branch -M main`
   - `git push -u origin main`
   If git asks for authentication, tell me exactly what to click (Git Credential Manager opens a
   browser window to sign in to GitHub).
4. Finish with the ✅/❌ checklist for Parts A, B and C, and the exact commands to run the app locally
   from PowerShell.
