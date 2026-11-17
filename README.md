# OnaRadar

AI early-warning registry for pregnant women and newborns (national AI hackathon problem #9):
Red / Yellow / Green zones from clinical rules + trend rules + an ML model, with explanations in Uzbek,
alerts to OvaBMU specialists with an SLA and escalation, and a de-identified AI summary.
**Decision support, not diagnosis. All demo data is synthetic.**

## Run (Windows, prototype mode: SQLite, no Docker)
Requirements: Python 3.11+, Node 20+.

```bat
start_all.bat          :: opens backend (:8000) and frontend (:5173) in two windows, then the browser
```
Or separately: `run_backend.bat`, `run_frontend.bat`. First backend run creates `backend\.venv`, installs
packages, trains the model (~1 min) and seeds the DB.

| Script | What it does |
|---|---|
| `reset_demo.bat` | Re-seeds the demo DB in ~10 s (stop the backend first) |
| `train_model.bat` | Regenerates synthetic data and retrains; prints ROC-AUC / PR-AUC |
| `run_tests.bat` | Backend tests (pytest) |

Config: `backend\.env` (template: `backend\.env.example`). `ANTHROPIC_API_KEY` empty → AI summary uses the
template fallback (tagged "Shablon"); with a key it calls `LLM_MODEL` (tagged "AI (Claude)").
`DEMO_MODE=true` → red-alert SLA is 2 minutes so escalation can be shown live.

## Demo users (password `demo1234`)
`nurse.nukus`, `doctor.nukus`, `specialist.nukus`, `admin.qoraqalpogiston`, `nurse.chilonzor`,
`specialist.chilonzor`, `admin.toshkent`, `admin.fargona` (+ nurse/doctor/specialist per district).

## Demo story (3 min)
1. Log in as **nurse.nukus** → Bemorlar → `QQR-NUK-DEMO1` (19 y, 31 weeks, **YELLOW**: fundal height lag + model).
2. **+ Yangi tashrif** → BP 152/98, protein **+2**, chip *Kuchli bosh og'rig'i* → live preview turns **RED**
   (R02 "Preeklampsiya shubhasi") before saving → Save → toast "Ogohlantirish yuborildi".
3. Log out → **specialist.nukus** → Ogohlantirishlar → red alert with SLA countdown → *Qabul qildim* + action.
4. Patient card → "Nega bu zona?" + **AI xulosa** (catalog actions only, disclaimer).

Other demo patients: `DEMO2` (37 y, previous CS, GDM glucose → stable YELLOW), `DEMO3` (healthy GREEN),
`DEMO4` (delivered; newborn with low birth weight + fast breathing → newborn RED).

## Layout
`backend/app` (FastAPI, SQLAlchemy, risk engine in `app/risk`, LLM in `app/llm`), `backend/ml` (generator,
training, model card), `frontend/` (React + TS + Vite + Tailwind), `docs/` (roadmap, clinical rules, API contract).
