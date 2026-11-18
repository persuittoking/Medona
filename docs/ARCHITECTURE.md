# OnaRadar — Architecture

## 1. Organizational Hierarchy & Tenancy
`Region → District → Polyclinic (oilaviy poliklinika, the TENANT) → Mahalla(s) → Patients`

- **Polyclinic as Tenant**: Every patient-level endpoint (`patients`, `visits`, `children`, `alerts`, `llm`, `polyclinic/map`, `dashboard`) is scoped through ONE central dependency: `Tenant` in `backend/app/api/tenancy.py`.
- **Multi-Mahalla Polyclinics**: A polyclinic serves `1..N` mahallas (e.g., `PL-SAM-003` in Samarqand serves 3 adjacent mahallas: `Registon MFY`, `Siyob MFY`, `Bog'ishamol MFY`). Each mahalla has its own patronage nurse (`User.mahalla_id`) who sees her mahalla's register by default and can switch to `"Barcha mahallalar"`. Doctors, OvaBMU specialists, and department heads oversee the entire polyclinic.
- **Mahalla Responsibility Principle**: The family polyclinic responsible for a woman's mahalla (`Mahalla.polyclinic_id`) is responsible for her care. `Patient.polyclinic_id` always equals the `polyclinic_id` of `Patient.mahalla_id` (enforced on creation and when moving mahallas via `assign_patient_mahalla` and a SQLAlchemy `before_flush` hook).
- **External Result Entry**: Staff of any polyclinic can record an analysis/visit (`POST /api/external/visits`) or infant check (`POST /api/external/checks`) for a patient from another clinic by exact JShShIR lookup (`POST /api/external/lookup` via `Patient.pinfl_hash`).
  - `Visit.performed_at_polyclinic_id` and `NewbornCheck.performed_at_polyclinic_id` store where the examination was performed (`NULL` = performed at the responsible clinic), alongside `entered_by`.
  - The visit/check is scored and saved under the **responsible polyclinic** (`Patient.polyclinic_id`). Any resulting alert is routed to the responsible polyclinic's OvaBMU specialist, and the responsible clinic sees `"Boshqa poliklinikada o'tkazilgan: <name>"` on the visit and a `"Tashqi natija kelib tushdi"` notification.
- **Admin Aggregates & Polyclinic Search**: District and region admins receive `403` on all patient-level endpoints and use `/api/geo/*` aggregate endpoints (counts only). `GET /api/geo/polyclinics/search?q=` provides accent-insensitive search across polyclinics and mahallas, returning aggregates and mahalla boundaries only.

## 2. Core Risk & Alert Pipeline
1. **Visit / Infant Check Entry**: Entered at the responsible clinic or via external entry.
2. **Risk Engine**:
   - **Pregnancies** (`backend/app/risk/`): Hard clinical red-flag rules (`R01–R10`), yellow rules (`Y01–Y16`, Tier A/B), 2-point and 3-point predictive trend rules (`T01–T05`, `P01–P05`), and calibrated LightGBM + SHAP (`ML can only raise a zone, never lower a rule-set zone`).
   - **Children 0–12 months** (`backend/app/risk/infant.py`): WHO IMCI neonatal/infant danger signs (`N01–N13`, `I01–I08`), WHO weight-for-age growth velocity (`G01–G02`), and national immunization schedule checks (`V01–V02`). Rules + trends only (no ML).
3. **Smart Alerts & Escalation (`backend/app/services/alerts.py`)**:
   - Triggered when a zone worsens (`green → yellow`, `* → red`).
   - **RED chain**: OvaBMU `specialist` (level 0) → OvaBMU `department_head` (level 1) → `district_admin` (level 2, count-only notification).
   - **YELLOW chain**: OvaBMU `specialist` (level 0) → polyclinic `doctor` (level 1) → `district_admin` (level 2, count-only notification).
   - Background APScheduler job (`every 30 s`) escalates overdue alerts.
4. **AI Summary (`backend/app/llm/`)**:
   - De-identified allow-list payload sent to Google Gemini (`google-genai` SDK) with structured output, fallback model, plain-JSON retry, and deterministic Uzbek template fallback (`"Shablon"`).
5. **Adaptive Visit Intensity (`backend/app/services/visit_intensity.py`)**:
   - The national standard of **12 mandatory antenatal visits** (`STANDARD_VISITS = 12`) is strictly respected and **never reduced**.
   - Each scheduled visit is assigned `"To'liq"` (full doctor visit) or `"Yengil"` (nurse-led standard check).
   - Eligibility requires `>= 3` (`CONSECUTIVE_GREEN_REQUIRED`) consecutive green assessments, no Tier B/A risk factors, no trend hits, no open alerts, and gestational age `< 36` weeks (from 36 weeks all visits stay `"To'liq"`).
   - Advisory only and never automatic: only the `doctor` role can confirm `"Yengil"` intensity (`POST /api/patients/{id}/visit-intensity/confirm`). Any yellow/red result or new risk factor resets all remaining visits to `"To'liq"` immediately. Every recommendation (`recommend_light_visit`), confirmation (`confirm_light_visit`), and reset (`reset_visit_intensity`) is written to `AuditLog`.
   - Dashboard shows `"Tejalgan shifokor vaqti"` = confirmed light visits × `MINUTES_SAVED_PER_LIGHT_VISIT` (default 10 min), labelled `"taxminiy, demo ma'lumot"`.
   - **Clinical & Ministry approval + "Vazirlikka taklif" (`PROPOSE_FEWER_VISITS=false`)**: Real-world intensity adjustments require clinical and Ministry of Health approval. A documented policy note (`"Vazirlikka taklif"`, OFF by default in `.env`, docs-only with no UI button) notes that a reduced schedule could be piloted in the future only if approved by the Ministry.
