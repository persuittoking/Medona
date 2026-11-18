# Task 15: Deploy OnaRadar as ONE web service (Railway, Docker)

Read CLAUDE.md first. EXTEND, do not rewrite. Never print, commit or hard-code secrets. Do NOT touch backend/.env.
Do NOT git push (the user pushes). Local `start_all.ps1` must keep working exactly as before.

## Goal
One Docker container serves both the API and the built React app from the same origin
(`https://<app>.up.railway.app` -> React; `/api/*` -> FastAPI). The frontend already calls relative `/api` paths, so
no API URL change is needed.

## Part A: Backend changes
1. Serve the built frontend: if `backend/static/index.html` exists, mount `backend/static/assets` as static files and add a
   catch-all GET route (registered AFTER all API routers) that returns `index.html` for any non-`/api` path (SPA routing).
   `/api/*` and `/docs` must keep working; unknown `/api/...` must still return JSON 404.
2. CORS: read `CORS_ORIGINS` (comma-separated) from settings; default stays `http://localhost:5173,http://127.0.0.1:5173`.
3. Startup on an empty database: add `backend/start.sh` (bash, LF line endings; add `*.sh text eol=lf` to .gitattributes) that
   - fails with a clear message if JWT_SECRET, PINFL_HASH_SECRET or FERNET_KEY is missing (never prints values);
   - runs `python -m app.seed` only if the SQLite file in DATABASE_URL does not exist yet;
   - never trains the model (the committed `backend/ml/artifacts/model.joblib` is used);
   - starts `uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'`.
4. Keep DEMO_MODE=true in the hosted demo (synthetic data). The login page must show the badge
   "Sintetik ma'lumot (demo)" and the list of demo logins as it does locally.
5. Basic abuse protection for a public URL: limit POST /api/auth/login to 20 attempts per IP per 10 minutes (in-memory is fine), test it.

## Part B: Docker
1. Root `Dockerfile`, multi-stage:
   - stage `web`: node:20-slim, `npm ci` + `npm run build` in frontend/;
   - stage `app`: python:3.11-slim, apt install `libgomp1` (LightGBM), `pip install --no-cache-dir -r backend/requirements.txt`,
     copy backend/, copy frontend `dist/` into `backend/static/`, WORKDIR backend, `CMD ["bash","start.sh"]`.
2. Root `.dockerignore`: .git, **/node_modules, **/.venv, **/__pycache__, **/*.db, **/.env, frontend/dist, backend/ml/data.
3. `railway.json`: builder DOCKERFILE, healthcheck path `/api/health`, restart policy ON_FAILURE.
4. Default DATABASE_URL in the container: `sqlite:////data/onaradar.db` if `/data` exists (Railway volume), else
   `sqlite:///./onaradar.db` (re-seeded on each deploy; fine for the demo). Document both.

## Part C: Verify locally
- If Docker is installed: `docker build -t onaradar .` and run with test secrets passed by `-e` (generate them, do not print),
  open http://localhost:8000, log in as PL-NUK-001 / nurse, check the map, a patient card and /api/health. Stop the container.
- If Docker is not installed, say so and instead run `npm run build`, copy dist to backend/static, start uvicorn, check the same
  pages, then delete backend/static (add `backend/static/` to .gitignore).
- ruff, pytest -q, frontend typecheck, lint, build must pass.

## Part D: Docs
Add `docs/DEPLOY.md` (English, short): Railway steps, the exact variable NAMES to set
(JWT_SECRET, PINFL_HASH_SECRET, FERNET_KEY, GEMINI_API_KEY, GEMINI_MODEL, GEMINI_FALLBACK_MODEL, DEMO_MODE, CORS_ORIGINS,
optional DATABASE_URL with a volume at /data), how to generate each secret, how to reset the hosted demo (redeploy / delete the
volume file), and a privacy note: hosted copy contains ONLY synthetic data; never put real patient data on it.

## Finish
ONE local commit "Deploy: single Docker service for Railway", do NOT push. Print a checklist with ✅/❌ for every numbered item.
