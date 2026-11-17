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

## Organisation
Region → District → **Polyclinic (oilaviy poliklinika, the tenant)** → Mahalla(s) → Patients.
Staff see only their own polyclinic (one central dependency, `backend/app/api/tenancy.py`), including patient
home points on the mahalla map. District/region admins see **aggregated counts only** (no names, codes or homes).

## Demo logins (password `demo1234`)
| Poliklinika ID | Login | Role |
|---|---|---|
| PL-NUK-001 | nurse / doctor / specialist | Nukus shahri — Navbahor MFY (DEMO1–4 live here) |
| PL-CHL-001 | nurse / doctor / specialist | Toshkent, Chilonzor — Qatortol MFY |
| PL-FRG-001 | nurse / doctor / specialist | Farg'ona shahri — Maʻrifat mahallasi |
| *(empty)* | district.admin | Nukus shahri (aggregates only) |
| *(empty)* | region.admin | Qoraqalpog'iston (aggregates only) |

## Demo story (3 min)
1. Login map: the polyclinic's mahalla on satellite imagery. Log in **PL-NUK-001 / nurse** → mahalla map with
   patient homes coloured by zone.
2. Bemorlar → `QQR-NUK-DEMO1` (19 y, 31 weeks, **YELLOW**: fundal height lag + model) → **+ Yangi tashrif** →
   BP 152/98, protein **+2**, *Kuchli bosh og'rig'i* → live preview turns **RED** (R02) → save.
3. Log in **PL-NUK-001 / specialist** → Ogohlantirishlar → red alert with SLA countdown → *Qabul qildim*.
4. Patient card → "Nega bu zona?" + **AI xulosa**.
5. Log in **region.admin** → O'zbekiston › Qoraqalpog'iston › Nukus shahri › PL-NUK-001: counts only.

Screenshots: `docs/screenshots/`. Boundary sources: `DATA_SOURCES.md`.

## Layout
`backend/app` (FastAPI, SQLAlchemy, tenancy in `app/api/tenancy.py`, risk engine in `app/risk`, LLM in `app/llm`), `backend/seed` (mahalla boundaries), `backend/ml` (generator,
training, model card), `frontend/` (React + TS + Vite + Tailwind), `docs/` (roadmap, clinical rules, API contract).
