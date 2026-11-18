# OnaRadar — project context for Claude Code

## What we are building
OnaRadar ("Ona" = mother + radar) is an AI early-warning system for pregnant women and
newborns in Uzbekistan. It is the solution to national AI hackathon problem #9:
"Perinatal yuqori xavf guruhi registri (Rang zonalari monitoringi)" — monitor pregnant women
and newborns with Red / Yellow / Green zones and automatically notify OvaBMU specialists
when results get worse.

Organisation: Region → District → Polyclinic (oilaviy poliklinika, the TENANT) → Mahalla(s) → Patients.
All patient-level access goes through backend/app/api/tenancy.py (filter by polyclinic_id). Admins see aggregates only.

Users and roles:
- `nurse` (patronaj hamshirasi): enters visits for patients in her mahalla, mobile-first.
- `doctor` (oilaviy shifokor): sees all patients in the district, enters visits.
- `specialist` (OvaBMU mutaxassisi): receives alerts, must acknowledge red alerts within the SLA.
- `district_admin` / `region_admin`: aggregated maps (counts only, no names or home points), model analytics, audit log.

Core loop: a visit is saved → the risk engine scores it (clinical rules + trend rules + ML)
→ a zone is assigned → if the zone gets worse (especially → RED), an alert is created
→ a Telegram notification goes out → if nobody acknowledges within the SLA, it escalates to the
next level → everything is logged.

## Non-negotiable principles
1. **Decision support, not diagnosis.** The UI and the AI text always say the final decision belongs
   to the doctor. Never output a diagnosis; say "xavf belgisi" / "shubha" (risk sign / suspicion).
2. **Explainability.** Every zone must show *why*: which clinical rule fired, which trend,
   and the top ML factors (SHAP), in plain Uzbek.
3. **Safety first.** Hard clinical red-flag rules ALWAYS override the ML model. The ML model can
   only raise a zone, never lower a zone set by rules.
4. **Privacy (medical secrecy + Law ZRU-547 "On Personal Data").** Full name and JShShIR (PINFL)
   are encrypted at rest and masked in the UI by default. The LLM and Telegram never receive name,
   JShShIR, phone or address — only the pseudonymous patient code + clinical features.
   Every view of a patient card is written to the audit log. Role-based access everywhere.
5. **Honest data.** All demo data is synthetic and every screen that shows it carries a small badge
   "Sintetik ma'lumot (demo)".
6. **Demo must never fail.** Every external dependency (LLM API, Telegram) has an offline fallback,
   and the app runs fully with `docker compose up` and no internet except those optional services.

## Tech stack — what the prototype really uses (keep to this; don't add frameworks without asking)
- Backend: Python 3.11+, FastAPI, SQLAlchemy 2.0, Pydantic v2, **SQLite** (`DATABASE_URL`), JWT auth
  (python-jose), bcrypt, cryptography (Fernet) for field encryption + HMAC-SHA256 for the JShShIR lookup hash,
  APScheduler for SLA escalation. No Alembic yet: `create_all` + a non-destructive `ensure_columns` upgrade.
- ML: pandas, numpy, scikit-learn, LightGBM, SHAP, joblib. Model artifacts in `backend/ml/artifacts/`.
- LLM: Google Gemini via the official `google-genai` SDK. Env: `LLM_PROVIDER=gemini`, `GEMINI_API_KEY`,
  `GEMINI_MODEL` / `GEMINI_FALLBACK_MODEL` (see `backend/.env.example`), `LLM_TIMEOUT_S` (default 25). Structured
  JSON output, fallback model, one plain-JSON retry, then the template fallback ("Shablon").
  Only the de-identified allow-list payload is sent. Real patient data requires a PAID Gemini API tier.
- Telegram: a **send-only adapter** in `backend/app/services/notify.py` (Bot API over HTTPS; logs "offline" without a
  token). No aiogram bot service yet.
- Frontend: React 18 + TypeScript + Vite, Tailwind CSS (own small components, no shadcn/ui), TanStack Query,
  React Router, Recharts, react-leaflet (Esri satellite / OpenStreetMap tiles). Uzbek strings in `src/i18n/uz.ts`
  (no i18next yet).
- Infra: Windows `.bat` / `.ps1` scripts, pytest, ruff, eslint. No Docker, no CI yet.
- **Production plan:** PostgreSQL 16 + Alembic migrations, Docker Compose (db, backend, bot, frontend), an aiogram
  bot service, CI, and hosting inside Uzbekistan (personal-data localization, Law ZRU-547).

## Repo layout
backend/app/{main.py, config.py, db.py, models/, schemas/, api/, services/, risk/, llm/, security/}
backend/ml/{generate_synthetic.py, train.py, metrics_docs.py, artifacts/, MODEL_CARD.md}
backend/tests/
frontend/src/{pages/, components/, api/, i18n/, lib/}
docs/{ARCHITECTURE.md, CLINICAL_RULES.md, PRIVACY_AND_LEGAL.md, DEMO_SCRIPT.md, QA_PREP.md, CODE_TOUR.md,
      BUSINESS_MODEL.md}

## Language
- All user-facing text in **Uzbek (Latin script)**, clear and polite, using medical terms common in
  Uzbekistan (homiladorlik muddati, arterial bosim, gemoglobin, patronaj, perinatal markaz, OvaBMU).
- Code, comments, commit messages and docs: English.

## Working rules for you (Claude Code)
- Work phase by phase. Don't build features from later phases early.
- After each phase: run `pytest` (and the frontend build/lint if it was touched), fix failures,
  update docs, and print a short checklist of the phase's acceptance criteria with ✅/❌.
- Keep functions small and typed. Put clinical thresholds in ONE config file
  (`backend/app/risk/thresholds.py`), never hard-coded in several places.
- Never invent statistics in UI text or docs. Real-world numbers live only in
  `docs/PITCH_FACTS.md`, with their source.

## Prototype mode (current)
Use SQLite (DATABASE_URL=sqlite:///./onaradar.db) and run WITHOUT Docker until told otherwise.
We are on Windows: provide .bat scripts and Windows-friendly commands.
