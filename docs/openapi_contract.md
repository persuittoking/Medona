# OnaRadar API contract (prototype)

Base URL: `http://localhost:8000`. Interactive docs: `/docs` (Swagger UI). Schemas: `backend/app/schemas/__init__.py`.
All endpoints except `/api/health` and `/api/auth/login` need `Authorization: Bearer <JWT>`.

**Tenancy:** every patient-level endpoint is limited to the caller's **polyclinic** by ONE dependency
(`backend/app/api/tenancy.py`). Another polyclinic's ids return **404** (no existence leak). District/region admins get
**403** on all patient-level endpoints and use the aggregate `/api/geo/*` endpoints instead.

| Method | Path | Roles | Description |
|---|---|---|---|
| GET | `/api/health` | — | `{status, demo_mode, model_version, llm: "ai"\|"template"}` |
| POST | `/api/auth/login` | — | `{polyclinic_code, username, password}` → `{access_token, user}`; admins send no `polyclinic_code` |
| GET | `/api/auth/me` | all | current user |
| GET | `/api/patients` | staff | own polyclinic. Filters: `zone`, `mahalla_id`, `trimester`, `overdue`, `q`. |
| GET | `/api/patients/{patient_id}` | staff | card: masked PII, home point, pregnancy, visits, assessments, alerts, newborns. **Writes audit `view_patient`.** |
| POST | `/api/patients/{patient_id}/reveal` | staff | full name / PINFL / phone. **Writes audit `reveal_pii`.** |
| POST | `/api/risk/preview` | staff | `VisitIn` → `RiskOut`. Scores WITHOUT saving (live form preview). |
| POST | `/api/visits` | nurse, doctor | `VisitIn` → `{visit, assessment, previous_zone, alert}`; creates an Alert if the zone got worse. |
| GET | `/api/alerts` | staff | filters: `status` (`active` = open+escalated, or exact), `level`, `mine`. Runs SLA escalation first. |
| POST | `/api/alerts/{id}/ack` | specialist, doctor | `{action_taken}` (required, ≥3 chars) |
| POST | `/api/alerts/{id}/resolve` | specialist, doctor | `{action_taken}` |
| GET | `/api/dashboard/summary` | staff | KPIs: active, red/yellow/green, open alerts, SLA breaches, median minutes to acknowledge |
| GET | `/api/dashboard/trend` | staff | weekly distinct pregnancies with red / yellow assessments, last 12 weeks |
| GET | `/api/dashboard/top` | staff | top-10 highest-risk active pregnancies with main reason |
| GET | `/api/polyclinic/map` | staff | own mahalla polygons + patient home points (zone-coloured). Audit `view_home_points`. |
| GET | `/api/public/territories` | — | demo polyclinic territory outlines only (login map) |
| GET | `/api/geo/country` | admins | regions with aggregated counts (other regions: `accessible=false`, no counts) |
| GET | `/api/geo/regions/{id}` | admins | districts with counts |
| GET | `/api/geo/districts/{id}` | admins | polyclinics with counts + territory polygons |
| GET | `/api/geo/polyclinics/{id}` | admins | one polyclinic: counts + territory + breadcrumb. **Never** names, codes or home points |
| GET | `/api/analytics/model` | all | `ml/artifacts/metrics.json` |
| GET | `/api/audit` | admins | own district/region staff; filters `action`, `entity` |
| GET | `/api/llm/summary/{pregnancy_id}` | staff | AI summary (de-identified input) with template fallback; `?refresh=true` regenerates. `source`: `ai` \| `template` |

## VisitIn
```json
{ "pregnancy_id": 1, "visit_date": "2026-11-17", "systolic": 152, "diastolic": 98, "proteinuria": "+2",
  "hemoglobin_g_l": 103, "fasting_glucose_mmol": 4.6, "weight_kg": 66.4, "temperature_c": 36.7,
  "fetal_heart_rate": 142, "fundal_height_cm": 30, "symptoms": ["severe_headache"], "notes": "..." }
```
`proteinuria`: `neg | trace | +1 | +2 | +3`. `symptoms`: `bleeding, severe_headache, visual_disturbance,
epigastric_pain, seizures, dyspnea, reduced_fetal_movement, contractions, membrane_rupture, edema`.
Gestational weeks are computed from LMP. Physiologically impossible values → `422`.

## RiskOut
```json
{ "zone": "red", "ml_probability": 0.82,
  "rule_hits": [{"code": "R02", "zone": "red", "uz_text": "Preeklampsiya shubhasi (AB 152/98, proteinuriya +2)"}],
  "trend_hits": [{"code": "T05", "zone": "yellow", "uz_text": "..."}], "notes": ["Yengil anemiya ..."],
  "shap_top": [{"feature": "systolic", "value": 152, "shap": 0.9, "direction": "up", "uz_label": "Sistolik bosim 152"}],
  "model_version": "e07aca5c61", "explanation_uz": "Zona: QIZIL. ..." }
```

## Alert SLA
RED: `SLA_RED_MINUTES` (120; **2 minutes in `DEMO_MODE=true`**). YELLOW: `SLA_YELLOW_HOURS` (72).
Escalation every 30 s: polyclinic specialist → polyclinic doctor (level 1) → district admin (level 2, notification only — sees counts, not the patient); status `escalated`.
