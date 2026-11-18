# OnaRadar — code tour

A one-page map per area: what each file is for. Start at `backend/app/main.py` (backend) and
`frontend/src/main.tsx` (frontend).

## 1. Backend core (`backend/app/`)
| File | Purpose |
|---|---|
| `main.py` | FastAPI app: startup checks secrets (DEMO_MODE=false refuses weak ones), creates/upgrades tables, syncs JShShIR hashes, loads the model, starts the scheduler, mounts routers |
| `config.py` | Settings from `backend/.env` (pydantic-settings); `check_secrets()`; demo SLA |
| `db.py` | Engine + session; `ensure_columns` (non-destructive upgrade); `sync_pinfl_hashes` (re-hash after a key change) |
| `models/__init__.py` | All ORM tables: Region → District → Polyclinic → Mahalla → Patient → Pregnancy → Visit; Newborn + checks; RiskAssessment; Alert + AlertEvent + ContactAttempt; QualityFlag; AuditLog; AppMeta |
| `schemas/__init__.py` | Pydantic request/response models (input ranges are validated here) |
| `scheduler.py` | APScheduler: escalation + closed-loop follow-ups every 30 s; AI-summary pre-warm |
| `seed.py` | Synthetic demo register (4 polyclinics, 6 mahallas, DEMO1–DEMO5, trend patients), scored by the real engine |
| `geo.py` | Region / district reference data (approximate centres) |
| `make_env.py` | First run: writes `backend/.env` with fresh JWT_SECRET, PINFL_HASH_SECRET, FERNET_KEY |

## 2. API (`backend/app/api/`)
| File | Purpose |
|---|---|
| `tenancy.py` | **The one place** that decides patient-level access (polyclinic = tenant; other tenant → 404; admins → 403). Also the rate-limited, audited cross-polyclinic lookup |
| `deps.py` | Current user, admin guard, `audit()` helper |
| `auth.py` | Login (polyclinic code + username), `/me` |
| `patients.py` / `children.py` | Lists and cards (PII masked, every card view audited), infant checks |
| `visits.py` | Visit save → score → alert → closed-loop hook; external (other-polyclinic) entry |
| `alerts.py` | Alert inbox, ack, resolve (needs a new measurement), confirm (two-person rule), contact attempts, reassign, demo SLA button |
| `care_loop.py` | "Sifat nazorati" (quality signals), patient transfer to a new mahalla |
| `dashboard.py` | KPIs, trend, top-risk list, model analytics, audit log (admins) |
| `geo.py` | Mahalla map (nurse: red points only), admin aggregate drill-down (counts only), polyclinic search |
| `llm.py` | AI summary (async, cached), admin LLM health (no key, counts only) |

## 3. Risk engine (`backend/app/risk/`)
| File | Purpose |
|---|---|
| `thresholds.py` | **All** clinical and workflow thresholds (single source of truth) |
| `rules.py` | Hard RED rules R01–R10, YELLOW rules Y01–Y16 (Tier A/B) |
| `trends.py` | 2-point trends T01–T05, predictive 3-point trends P01–P05 |
| `features.py` | Feature building shared by training and live scoring |
| `ml.py` | Calibrated LightGBM + SHAP top factors (Uzbek labels) |
| `engine.py` | Final zone = max(rules, trends, ML): ML can only raise a zone |
| `newborn.py` / `infant.py` | Newborn (N01–N13) and 0–12-month (I01–I14, G01–G02, vaccines) rules |

## 4. LLM (`backend/app/llm/`)
| File | Purpose |
|---|---|
| `summary.py` | De-identified allow-list payload → Gemini (structured JSON) → fallback model → plain retry → template "Shablon" |
| `actions.py` | Action catalog A01–A28: the only actions the AI may recommend (also used for structured alert closure) |
| `safety.py` | Rejects AI text with diagnosis wording or digit runs that look like JShShIR / phone |

## 5. Security (`backend/app/security/`)
| File | Purpose |
|---|---|
| `crypto.py` | Fernet encryption of name / JShShIR / phone / home; keyed HMAC hash for exact JShShIR lookup; masking |
| `auth.py` | Password hashing (bcrypt) and JWT |

## 6. Services (`backend/app/services/`)
| File | Purpose |
|---|---|
| `scoring.py` | Glue between ORM rows and the pure risk engine; alert created only when the zone gets worse |
| `alerts.py` | Escalation chain (one place), SLA, alert serialization |
| `closed_loop.py` | Proof of care: ack ≠ close, closure needs a new measurement, two-person rule, reopen, unreachable workflow, transfer |
| `quality.py` | Plausibility signals per user (signal, not accusation) + department-head tiles |
| `ai_summary.py` | Summary cache, background generation, demo pre-warm, demo-summary status (counts) |
| `notify.py` | Send-only Telegram adapter (de-identified text; "offline" log without a token) |
| `children.py` | Child scoring and check storage |
| `visit_intensity.py` | 12 mandatory visits, To'liq / Yengil advice, doctor-only confirmation |
| `geo.py` | Point-in-polygon, home-point encryption, mahalla assignment |

## 7. ML pipeline (`backend/ml/`)
`generate_synthetic.py` (synthetic cohort) → `train.py` (LightGBM, calibration, thresholds, `artifacts/metrics.json`)
→ `metrics_docs.py` (writes the metrics block in MODEL_CARD.md and README.md). `MODEL_CARD.md` explains limits.

## 8. Frontend (`frontend/src/`)
| Path | Purpose |
|---|---|
| `main.tsx` | Routes; `api/client.ts` fetch wrapper with JWT; `api/types.ts` API types |
| `pages/Dashboard.tsx` | KPIs, map, top-risk list; department-head tiles |
| `pages/PolyclinicMap.tsx` | Mahalla map (nurse: red only, no polyclinic search) |
| `pages/Patients.tsx`, `PatientCard.tsx`, `ChildCard.tsx` | Register and cards: zone explanation, visits, alerts with proof-of-care actions |
| `pages/NewVisit.tsx`, `NewChildCheck.tsx`, `ExternalVisit.tsx` | Data entry with live risk preview |
| `pages/Alerts.tsx` | Alert inbox: SLA timer, 3-bullet summary, ack / close / confirm, escalation history |
| `pages/Quality.tsx` | "Sifat nazorati" (department head) |
| `pages/GeoDrilldown.tsx`, `Misc.tsx` | Admin aggregates, model analytics, audit, about |
| `components/` | `MahallaMap` (Leaflet), `AlertLoop` (closed-loop dialogs), `RiskExplain`, `AiSummaryPanel`, `SubjectSwitch`, `ui` |
| `i18n/uz.ts`, `lib/` | Uzbek labels; auth context, formatting, toasts, subject switch |

## 9. Tests (`backend/tests/`, pytest)
`conftest.py` seeds a fresh small DB per module. Main groups: `test_risk_engine`, `test_predictive_trends`,
`test_infant_engine` (clinical logic) · `test_tenancy` (isolation guard for every patient endpoint) · `test_api`,
`test_children_api`, `test_smart_alerts` (flows) · `test_llm*` (fallback chain, privacy of the payload) ·
`test_task09`–`test_task14` (mahalla responsibility, nurse map, proof of care, security hygiene, docs vs metrics).
