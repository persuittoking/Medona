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
| GET | `/api/patients/{patient_id}` | staff | card: masked PII, home point, pregnancy, `visit_plan` (12 mandatory visits with `"To'liq"`/`"Yengil"` intensity), visits, assessments, alerts, newborns. **Writes audit `view_patient` (and `recommend_light_visit` when eligible).** |
| POST | `/api/patients/{patient_id}/visit-intensity/confirm` | doctor | confirm `"Yengil"` visit intensity for an eligible pregnancy (never reduces 12 visits; audit `confirm_light_visit`) |
| POST | `/api/patients/{patient_id}/reveal` | staff | full name / PINFL / phone. **Writes audit `reveal_pii`.** |
| POST | `/api/risk/preview` | staff | `VisitIn` → `RiskOut`. Scores WITHOUT saving (live form preview). |
| POST | `/api/visits` | nurse, doctor | `VisitIn` → `{visit, assessment, previous_zone, alert}`; creates an Alert if the zone got worse. |
| GET | `/api/alerts` | staff | filters: `status` (`active` = open+escalated, or exact), `level`, `mine`, `escalated` (level ≥1). Each alert: `summary_bullets` (3) + `summary_source` + `summary_status` (`ready`/`pending`/`unavailable`), `trend_driven`, `assigned_role`, `next_role`, `history[]`. Escalation runs in the background job, not here. |
| GET | `/api/alerts/assignees` | department_head | specialists of the own polyclinic |
| POST | `/api/alerts/{id}/ack` | specialist, doctor, department_head | `{action_taken}` (required, ≥3 chars) |
| POST | `/api/alerts/{id}/resolve` | specialist, doctor, department_head | `{action_taken}` |
| POST | `/api/alerts/{id}/reassign` | department_head | `{user_id, note?}` → a specialist of the same polyclinic; SLA restarts; audit `reassign_alert`; Telegram to the new assignee |
| GET | `/api/settings/sla` | department_head, admins | read-only SLA values + escalation chain |
| GET | `/api/dashboard/summary` | staff | KPIs: active, red/yellow/green, open alerts, SLA breaches, median minutes to acknowledge |
| GET | `/api/dashboard/trend` | staff | weekly distinct pregnancies with red / yellow assessments, last 12 weeks |
| GET | `/api/dashboard/top` | staff | top-10 highest-risk active pregnancies with main reason |
| GET | `/api/polyclinic/map` | staff | own mahalla polygons + patient home points (zone-coloured). Audit `view_home_points`. |
| GET | `/api/public/territories` | — | demo polyclinic territory outlines only (login map) |
| GET | `/api/geo/country` | admins | regions with aggregated counts (other regions: `accessible=false`, no counts) |
| GET | `/api/geo/regions/{id}` | admins | districts with counts |
| GET | `/api/geo/districts/{id}` | admins | polyclinics with counts + territory polygons |
| GET | `/api/geo/polyclinics/{id}` | admins | one polyclinic: counts + territory + `mahallas[]` (per-mahalla counts) + breadcrumb. **Never** names, codes or home points |
| GET | `/api/geo/polyclinics/search?q=&subject=` | all | accent-insensitive search by polyclinic name, code, city, or mahalla name; returns **aggregates + mahalla boundaries only** |
| POST | `/api/external/lookup` | nurse, doctor | `{pinfl}` → `{patient_code, responsible_polyclinic_id, responsible_polyclinic_code, responsible_polyclinic_name, mahalla_name, has_active_pregnancy, children[]}` (exact match via HMAC-SHA256 `pinfl_hash`, rate-limited 30/h, audit `external_lookup` / `external_lookup_miss`) |
| POST | `/api/external/visits` | nurse, doctor | external pregnancy visit (`ExternalVisitIn`) → scored & saved under the responsible clinic with `performed_at_polyclinic_id`; audit `external_entry` with both polyclinic IDs |
| POST | `/api/external/checks` | nurse, doctor | external infant check (`ExternalCheckIn`) → scored & saved under the responsible clinic with `performed_at_polyclinic_id`; audit `external_entry` with both polyclinic IDs |
| GET | `/api/external/notifications` | staff | recent external visits/checks received by the responsible polyclinic (`"Tashqi natija kelib tushdi"`) |
| GET | `/api/analytics/model` | all | `ml/artifacts/metrics.json` |
| GET | `/api/audit` | admins | own district/region staff; filters `action`, `entity` |
| GET | `/api/children?zone&q&status=active` | staff | children 0–12 months of this polyclinic (tenant key copied from the mother) |
| GET | `/api/children/{newborn_id}` | staff | child card: zone, explanation, checks, weight-for-age points + WHO reference, vaccine status, alerts. **Writes audit `view_child`.** |
| POST | `/api/children/risk/preview` | staff | score an infant check without saving (live preview) |
| POST | `/api/children/checks` | nurse, doctor | save an infant check → score → alert if the zone gets worse (`Alert.newborn_id`) |
| GET | `/api/llm/summary/child/{newborn_id}` | staff | AI summary for a child (child allow-list payload: age in months, sex, last 3 checks, hits) |
| — | `?subject=pregnancy\|child\|all` | — | on `/api/dashboard/*`, `/api/alerts`, `/api/geo/*` (admin geo answers include `subject_counts`) |
| GET | `/api/llm/summary/{pregnancy_id}` | staff | AI summary (de-identified input) with template fallback, cached per assessment and generated in the background: **202** `{"status":"pending"}` until ready, then 200 `{"status":"ready", ...}` (poll every 3 s). `?refresh=true` regenerates. `source`: `ai` \| `template` |

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
RED: `SLA_RED_MINUTES` (120; **`DEMO_SLA_RED_MINUTES`, default 10, in `DEMO_MODE=true`**). YELLOW: `SLA_YELLOW_HOURS` (72).
`POST /api/alerts/{id}/demo-expire-sla` (specialist or department_head, `DEMO_MODE` only, else 404): sets `sla_due_at` to now so the
next escalation run (≤30 s) escalates it; audit action `demo_expire_sla`.
Escalation every 30 s: polyclinic specialist → polyclinic doctor (level 1) → district admin (level 2, notification only — sees counts, not the patient); status `escalated`.
