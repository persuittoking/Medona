# OnaRadar — project context for Claude Code

## What we are building
OnaRadar ("Ona" = mother + radar) is an AI early-warning system for pregnant women and
newborns in Uzbekistan. It is the solution to national AI hackathon problem #9:
"Perinatal yuqori xavf guruhi registri (Rang zonalari monitoringi)" — monitor pregnant women
and newborns with Red / Yellow / Green zones and automatically notify OvaBMU specialists
when results get worse.

Users and roles:
- `nurse` (patronaj hamshirasi): enters visits for patients in her mahalla, mobile-first.
- `doctor` (oilaviy shifokor): sees all patients in the district, enters visits.
- `specialist` (OvaBMU mutaxassisi): receives alerts, must acknowledge red alerts within the SLA.
- `admin` (viloyat sog'liqni saqlash boshqarmasi): regional dashboard, model analytics, audit log.

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

## Tech stack (keep to this; don't add frameworks without asking)
- Backend: Python 3.11, FastAPI, SQLAlchemy 2.0, Pydantic v2, Alembic, PostgreSQL 16
  (SQLite allowed via `DATABASE_URL` for local tests), JWT auth (python-jose), passlib[bcrypt],
  cryptography (Fernet) for field encryption, APScheduler for SLA escalation.
- ML: pandas, numpy, scikit-learn, LightGBM, SHAP, joblib. Model artifacts in `backend/ml/artifacts/`.
- LLM: Anthropic Python SDK, model from env `LLM_MODEL` (default `claude-sonnet-5-5`),
  key from env `ANTHROPIC_API_KEY`. Template fallback when the key is missing or the call fails.
- Telegram: aiogram 3, runs as a separate service, polling mode.
- Frontend: React 18 + TypeScript + Vite, Tailwind CSS, shadcn/ui, TanStack Query, React Router,
  Recharts, react-leaflet (OpenStreetMap tiles), i18next (uz-Latn default, ru optional).
- Infra: Docker Compose (db, backend, bot, frontend), pytest, ruff, eslint, GitHub Actions CI.

## Repo layout
backend/app/{main.py, config.py, db.py, models/, schemas/, api/, services/, risk/, llm/, security/}
backend/ml/{generate_synthetic.py, train.py, artifacts/, MODEL_CARD.md}
backend/tests/
bot/
frontend/src/{pages/, components/, api/, i18n/, lib/}
docs/{ARCHITECTURE.md, CLINICAL_RULES.md, PRIVACY_AND_LEGAL.md, DEMO_SCRIPT.md, QA_PREP.md}

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
