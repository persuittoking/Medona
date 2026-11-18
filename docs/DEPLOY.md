# Deploying the OnaRadar demo (Railway, one Docker service)

One container serves everything from the same origin:
`https://<app>.up.railway.app/` → React app, `/api/*` → FastAPI, `/docs` → OpenAPI UI.
The frontend already calls relative `/api` paths, so no API URL is configured anywhere.

Files: `Dockerfile` (node build stage → python:3.11-slim), `.dockerignore`, `railway.json`
(Dockerfile builder, healthcheck `/api/health`, restart ON_FAILURE), `backend/start.sh` (entrypoint).
Local development (`start_all.ps1`, Vite on :5173) is unchanged.

> **Privacy: the hosted copy contains ONLY synthetic data.** Never enter real patient data on it. Real data needs
> the production plan (PostgreSQL, hosting inside Uzbekistan under Law ZRU-547, a paid Gemini tier) — see
> `docs/PRIVACY_AND_LEGAL.md`.

## Railway steps
1. Push the repo to GitHub (the user does this).
2. Railway → **New Project → Deploy from GitHub repo** → pick the repo. Railway finds `railway.json` and builds the
   root `Dockerfile`.
3. Service → **Variables**: set the variables below.
4. Service → **Settings → Networking → Generate Domain**. Open it and log in as `PL-NUK-001` / `nurse` / `demo1234`.
5. Optional, to keep data between deploys: **add a Volume mounted at `/data`** (see "Database").

The first start seeds the synthetic register (~1 minute) before uvicorn listens; the healthcheck timeout is 300 s.

## Variables (names only — never commit values)
| Variable | Required | Value / how to generate |
|---|---|---|
| `JWT_SECRET` | yes | `python -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `PINFL_HASH_SECRET` | yes | same command, a **different** value than `JWT_SECRET` |
| `FERNET_KEY` | yes | `python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"` |
| `DEMO_MODE` | recommended | `true` (default in the container: synthetic data, demo logins on the login page) |
| `GEMINI_API_KEY` | optional | Google AI Studio key; empty → template summaries ("Shablon") |
| `GEMINI_MODEL` | optional | e.g. `gemini-3.1-flash-lite` (see `backend/.env.example`) |
| `GEMINI_FALLBACK_MODEL` | optional | e.g. `gemini-3.5-flash-lite` |
| `CORS_ORIGINS` | optional | comma-separated; not needed for the single-origin deploy (default `http://localhost:5173,http://127.0.0.1:5173`) |
| `DATABASE_URL` | optional | leave unset (see below) |

`start.sh` refuses to start if `JWT_SECRET`, `PINFL_HASH_SECRET` or `FERNET_KEY` is missing (it prints only the names).
Railway sets `PORT`; uvicorn runs with `--proxy-headers` so the real client IP is used.

## Database
`DATABASE_URL` unset → `start.sh` picks:
- `sqlite:////data/onaradar.db` if `/data` exists (Railway volume) — data survives redeploys;
- otherwise `sqlite:///./onaradar.db` inside the container — a **fresh synthetic DB on every deploy** (fine for the demo).

Seeding (`python -m app.seed`) runs only when that SQLite file does not exist yet. The model is never trained in the
container; the committed `backend/ml/artifacts/model.joblib` is used.

## Reset the hosted demo
- Without a volume: **Redeploy** the service (new container → re-seeded).
- With a volume: delete `/data/onaradar.db` (e.g. `railway ssh` → `rm /data/onaradar.db`, or delete/recreate the
  volume), then redeploy/restart.

## Abuse protection
`POST /api/auth/login` is limited to 20 attempts per client IP per 10 minutes (in memory, per process;
`LOGIN_RATE_LIMIT`, `LOGIN_RATE_WINDOW_S`). A restart clears it.

## Run the same image locally
```
docker build -t onaradar .
docker run --rm -p 8000:8000 --env-file my-secrets.env onaradar   # file with the three secrets, never committed
```
Then open http://localhost:8000.
