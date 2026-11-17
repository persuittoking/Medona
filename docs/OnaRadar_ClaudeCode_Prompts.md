# OnaRadar — Claude Code prompt pack
**Team: Code · Umummilliy AI Xakaton 2026 · Problem #9 (Perinatal high-risk registry)**

## How to use this file
1. Create an empty folder `onaradar/`, open Claude Code inside it.
2. **Phase 0:** paste the `CLAUDE.md` block below into a file `CLAUDE.md` at the repo root. Claude Code reads it automatically every session, so every phase follows the same rules.
3. Paste the phase prompts **one at a time**, in order. Before each phase, press `Shift+Tab` to enter **plan mode**, read the plan, then approve it. After each phase: run the tests, check the acceptance list, then `git commit`.
4. **Run in parallel:** after Phase 1, the API contract is fixed. One teammate can then run Phase 5 (frontend) in a second Claude Code session while Phases 2–4 continue on the backend.
5. If something breaks, don't patch it by hand. Tell Claude Code: *"Acceptance item X fails with this error: … Fix it, and add a test that would have caught it."*

Suggested schedule:
| When | Phases |
|---|---|
| Day 1 evening (tonight) | 0, 1, 2, 3 (backend + ML), and start 5 (frontend) in parallel |
| Day 2 | 4, 5, 6, 7, 8 |
| Day 3 morning | 9 (demo + polish), 10 (docs + Q&A prep), rehearse the pitch |
| Only if time allows | 11 (stretch features) |

---

## PHASE 0 — `CLAUDE.md` (save as a file at the repo root)

```markdown
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
```

---

## PHASE 1 — Skeleton, data model, API contract

```
Read CLAUDE.md. Phase 1: project skeleton, data model and API contract.

1. Create the repo layout from CLAUDE.md, docker-compose.yml (postgres, backend, bot, frontend),
   .env.example (DATABASE_URL, JWT_SECRET, FERNET_KEY, ANTHROPIC_API_KEY, LLM_MODEL,
   TELEGRAM_BOT_TOKEN, DEMO_MODE, SLA_RED_MINUTES, SLA_YELLOW_HOURS), a Makefile
   (make up, make seed, make test, make train), and a backend health endpoint GET /api/health.

2. SQLAlchemy models + Alembic migration:
   - Region (14: Qoraqalpog'iston Respublikasi, 12 viloyat, Toshkent shahri) with lat/lon.
   - District (real district/tuman names, at least 4 per region, ~60+ total; lat/lon of the
     district centre).
   - Facility (oilaviy poliklinika, tuman tibbiyot birlashmasi, perinatal markaz) linked to a district.
   - User (full_name, role: nurse|doctor|specialist|admin, district_id/region_id scope,
     telegram_chat_id nullable, password hash).
   - Patient (pseudonymous code like "QQR-NUK-00421", full_name_enc, pinfl_enc, phone_enc,
     birth_date, district_id, mahalla, distance_to_perinatal_km, assigned_nurse_id).
   - Pregnancy (patient_id, lmp_date, booking_date, gravidity, parity, previous_cs, history flags:
     stillbirth, preterm, miscarriages_count, preeclampsia, pph; chronic flags: diabetes,
     chronic_htn, heart, kidney, thyroid, epilepsy; multiple_pregnancy, rh_negative,
     interpregnancy_months, height_cm, booking_weight_kg, status active|delivered|closed,
     current_zone, current_risk_score).
   - Visit (pregnancy_id, visit_date, gestational_weeks (computed from LMP), systolic, diastolic,
     proteinuria (neg,trace,+1,+2,+3), hemoglobin_g_l, fasting_glucose_mmol, weight_kg,
     temperature_c, fetal_heart_rate, fundal_height_cm, symptoms (multi-select:
     bleeding, severe_headache, visual_disturbance, epigastric_pain, seizures, dyspnea,
     reduced_fetal_movement, contractions, membrane_rupture, edema), notes, entered_by).
   - Newborn (pregnancy_id, birth_date, gestational_weeks_at_birth, birth_weight_g, apgar_5,
     current_zone) and NewbornCheck (danger signs: not_feeding_well, convulsions,
     resp_rate, severe_chest_indrawing, temperature_c, movement_only_when_stimulated,
     jaundice_first_24h, jaundice_palms_soles, weight_g).
   - RiskAssessment (target pregnancy or newborn, visit/check id, zone, rule_hits JSON,
     trend_hits JSON, ml_probability, shap_top JSON, model_version, created_at).
   - Alert (risk_assessment_id, level red|yellow, status open|acknowledged|escalated|resolved,
     assigned_user_id, escalation_level 0..2, sla_due_at, acknowledged_at, action_taken text).
   - AuditLog (user_id, action, entity, entity_id, ip, created_at).

3. Field encryption helper (Fernet) for *_enc columns, and a mask function for PINFL
   ("3**********12").

4. Write the API contract FIRST as `docs/openapi_contract.md`, plus Pydantic schemas, covering:
   auth/login, me; patients list/detail/create; pregnancies; visits create (returns the new
   risk assessment) and POST /api/risk/preview (score WITHOUT saving — used for live preview
   while typing); newborns + checks; alerts list/ack/resolve; dashboard/summary,
   dashboard/districts (counts per zone per district with lat/lon), dashboard/trend (weekly red/yellow
   counts); analytics/model (metrics); audit (admin only); llm/summary/{pregnancy_id}.
   Endpoints may return 501 for now — the contract matters more than the implementation in this phase.

Acceptance: docker compose up starts db+backend, /api/health returns ok, alembic migration
runs, pytest passes a smoke test, docs/openapi_contract.md exists and matches the schemas.
```

---

## PHASE 2 — Synthetic data generator

```
Read CLAUDE.md. Phase 2: realistic synthetic data in backend/ml/generate_synthetic.py.

Goal: ~20,000 pregnancies (configurable) across all regions/districts, each with 1–9 visits,
plus newborns for delivered pregnancies, AND an outcome label for ML training.

Rules for realism (document every assumption at the top of the file and in MODEL_CARD.md):
- Maternal age: mostly 20–34, with ~6% <18 or 18–19 and ~10% ≥35.
- Visits follow the antenatal schedule (booking, then roughly monthly, more often in the 3rd trimester);
  ~15% of women book late (>12 weeks) and some miss visits.
- Hemoglobin: mean ~112 g/L with SD ~13; regional shift (lower in Qoraqalpog'iston, Xorazm,
  Navoiy, Buxoro) to create believable regional differences.
- Blood pressure, glucose, BMI, fundal height (≈ gestational weeks ± 2 cm after 24 weeks),
  weight gain per week, fetal heart rate 120–160 normal: realistic distributions, with a subset of
  pregnancies that DETERIORATE over visits (rising BP + proteinuria; falling Hb; lagging fundal height).
- Outcome `adverse_outcome` (composite: severe preeclampsia/eclampsia, postpartum hemorrhage,
  preterm birth <34 weeks, stillbirth, neonatal intensive care). Generate it with a hidden
  logistic model over the risk factors + deterioration + noise, so the base rate is ~8–12%.
  The ML model must LEARN this; don't leak the label into the features.
- Newborns: birth weight from gestational age at birth; ~5–7% low birth weight; some danger signs.
- Patients get Uzbek names (synthetic, varied), synthetic PINFL (14 digits, not real), mahalla names.

Outputs:
- backend/ml/data/synthetic_pregnancies.parquet (one row per visit, with pregnancy features,
  visit features, deltas vs the previous visit, and the label)
- `make seed` command: loads a DB-sized subset (e.g. 3,000 active pregnancies + demo users)
  into Postgres, with encrypted PII.
- Demo users (password "demo1234"): nurse.nukus, doctor.nukus, specialist.nukus,
  admin.qoraqalpogiston, plus one of each for Toshkent shahri / Chilonzor.

Acceptance: the generator is deterministic with --seed; summary stats print (zone shares,
label rate, Hb mean by region); `make seed` fills the DB; tests check value ranges.
```

---

## PHASE 3 — Risk engine (rules + trends + ML + explanations)

```
Read CLAUDE.md. Phase 3: the risk engine in backend/app/risk/ and training in backend/ml/train.py.
Also write docs/CLINICAL_RULES.md with every rule, its threshold, its Uzbek explanation text,
and a reference source (WHO antenatal care recommendations, WHO anemia thresholds, WHO IMCI
young-infant danger signs, standard obstetric definitions). Mark it "to be verified by a clinician".

A) Clinical rules — antenatal (each rule has code, zone, uz_text):
RED (any one → RED):
 R01 systolic ≥160 or diastolic ≥110 (og'ir gipertenziya)
 R02 (systolic ≥140 or diastolic ≥90) AND proteinuria ≥ +1 (preeklampsiya shubhasi)
 R03 hemoglobin <70 g/L (og'ir anemiya)
 R04 vaginal bleeding at ≥20 weeks
 R05 danger symptoms: seizures, OR severe headache with visual disturbance, OR epigastric pain with BP ≥140/90, OR dyspnea
 R06 fetal heart rate <110 or >160 bpm (≥20 weeks, if measured)
 R07 reduced/absent fetal movement at ≥28 weeks
 R08 temperature ≥38.0°C
 R09 contractions or membrane rupture before 37 weeks (muddatidan oldin tug'ruq xavfi)
 R10 fasting glucose ≥7.0 mmol/L
YELLOW (any one → at least YELLOW):
 Y01 age <18 or ≥35            Y02 parity ≥5                 Y03 previous caesarean
 Y04 history: stillbirth, preterm birth, ≥2 miscarriages, previous preeclampsia or PPH
 Y05 systolic 140–159 or diastolic 90–109 without proteinuria
 Y06 hemoglobin 70–99 g/L      Y07 fasting glucose 5.1–6.9   Y08 booking BMI <18.5 or ≥30
 Y09 multiple pregnancy        Y10 chronic disease (any chronic flag)
 Y11 interpregnancy interval <24 months   Y12 Rh-negative
 Y13 late booking (>12 weeks) or overdue visit (>30 days in 3rd trimester, >45 days otherwise)
 Y14 ≥41 weeks and not delivered
 Y15 distance to perinatal centre >50 km combined with any other yellow factor (logistics risk)
Hemoglobin 100–109 is "yengil anemiya": show as a note, not a zone rule.

B) Trend rules (compare with the previous visit; each raises the zone at least to YELLOW,
   and two or more trend hits together → RED):
 T01 hemoglobin dropped ≥15 g/L      T02 systolic rose ≥20 or diastolic rose ≥15
 T03 weight gain >1.0 kg/week after 20 weeks (sudden edema)
 T04 fundal height ≥3 cm below gestational weeks after 24 weeks (fetal growth restriction suspicion)
 T05 ML probability rose by ≥0.15 since the previous visit

C) Newborn rules (WHO young-infant danger signs):
 RED: not feeding well, convulsions, respiratory rate ≥60, severe chest indrawing,
      temperature ≥37.5 or <35.5, movement only when stimulated, jaundice in first 24h or on
      palms/soles, birth weight <1500 g.
 YELLOW: birth weight 1500–2499 g, preterm <37 weeks, Apgar(5) <7, mother was RED in the
      3rd trimester, no postnatal check by day 3.

D) ML model (backend/ml/train.py):
 - LightGBM binary classifier on adverse_outcome, using pregnancy + visit + delta features.
 - Split BY PREGNANCY (no leakage), 5-fold CV, then probability calibration (isotonic).
 - Report ROC-AUC, PR-AUC, Brier score, sensitivity/specificity at the chosen thresholds,
   calibration curve, and metrics per region (fairness check). Save to artifacts/metrics.json
   and plots as PNG.
 - Thresholds: yellow and red probability cut-offs chosen on validation so that
   RED+YELLOW catches ≥90% of adverse outcomes; RED precision ≥ yellow precision.
   Store them in thresholds.py with the date and the metric that justified them.
 - SHAP TreeExplainer: top-5 factors per prediction with Uzbek feature labels
   (e.g. "Gemoglobin pasaygan (−18 g/L)", "Sistolik bosim 148").
 - Save model + feature list + version hash in artifacts/. Write backend/ml/MODEL_CARD.md
   (data, intended use, limits, "synthetic data — must be retrained on real DMED data").

E) Final zone = max(rule zone, trend zone, ML zone). The ML model can only RAISE the zone. Return:
 {zone, ml_probability, rule_hits[], trend_hits[], shap_top[], model_version, explanation_uz}

F) Tests: one test per rule (just above/below each threshold), trend tests, the
 "ML can't lower a red rule" test, newborn tests, and a test that the scoring time is <100 ms.

Acceptance: `make train` prints the metrics and writes the artifacts; the risk engine is importable
and fully tested; docs/CLINICAL_RULES.md is complete.
```

---

## PHASE 4 — API, auth, alerts, escalation, DMED adapter

```
Read CLAUDE.md. Phase 4: implement the API from docs/openapi_contract.md.

- JWT login, role-based access with scope (nurse → own patients, doctor/specialist → own district,
  admin → own region). A 403 test for each role boundary.
- POST visit → compute the risk (Phase 3 engine) → store the RiskAssessment → update the pregnancy's
  current_zone/current_risk_score → if the zone got worse, create an Alert:
  RED: sla_due = now + SLA_RED_MINUTES (default 120; in DEMO_MODE=true use 2 minutes)
  YELLOW: sla_due = now + SLA_YELLOW_HOURS (default 72)
  Assign it to the district's specialist.
- POST /api/risk/preview: the same scoring with no DB write (for the live form preview).
- Escalation job (APScheduler, every 30s): an open alert past its SLA → escalation_level+1,
  reassign: specialist → district chief doctor → regional admin; status=escalated; notify.
- Alert ack/resolve with a required short "action_taken" text (what the specialist did).
- Dashboard endpoints: summary KPIs (active pregnancies, red/yellow/green counts, open alerts,
  SLA breaches, median time-to-acknowledge), per-district zone counts with lat/lon,
  weekly trend of red/yellow over the last 12 weeks, top-10 highest-risk pregnancies.
- Analytics endpoint serving artifacts/metrics.json.
- AuditLog: middleware/dependency that writes every patient detail view, every create/update,
  every ack. Admin endpoint to read it with filters.
- DMED integration adapter (mock): POST /api/integrations/dmed/import accepting a FHIR-like
  Bundle (Patient + Observation resources with LOINC-style codes for BP, Hb, glucose, weight),
  mapping it to our Patient/Visit and scoring it. Document the mapping in docs/ARCHITECTURE.md
  ("Ready to plug into DMED: all state medical institutions are already connected to DMED").
- Event hook: when an Alert is created or escalated, push to an internal queue table
  `notification_outbox` (the bot will consume it in Phase 6). This avoids tight coupling.

Acceptance: pytest covers auth scopes, visit→alert flow, escalation after SLA (use freezegun),
audit entries, the DMED import mapping; Swagger UI at /docs works.
```

---

## PHASE 5 — Frontend (can run in parallel after Phase 1)

```
Read CLAUDE.md and docs/openapi_contract.md. Phase 5: React frontend in frontend/.
Design: clean medical look, white background, one accent colour (deep teal), zone colours
RED #DC2626 / YELLOW #F59E0B / GREEN #16A34A, always shown with a text label too (accessibility).
Mobile-first for nurse screens; desktop dashboards for specialist/admin. All text in Uzbek (Latin)
via i18next; add a Russian toggle with at least the menu + dashboard translated.

Pages:
1. /login — form + quick "Demo sifatida kirish" buttons for each role.
2. /dashboard — KPI cards (Faol homiladorlar, Qizil, Sariq, Yashil, Ochiq ogohlantirishlar,
   SLA buzilgan, O'rtacha javob vaqti); a Leaflet map of Uzbekistan with a circle per district
   (size = active pregnancies, colour = share of RED); a weekly red/yellow trend chart;
   a "Eng yuqori xavfli 10 nafar" table. Region/district filter for admin.
3. /patients — list with filters (zone, district, trimester, overdue visit), search by patient code,
   zone badges, last visit date, risk %.
4. /patients/:id — header: code, age, gestational weeks, zone badge, risk gauge;
   "Nega bu zona?" panel: rule hits + trend hits + SHAP bar chart in Uzbek;
   charts over visits for Hb, systolic/diastolic and weight, with threshold lines (e.g. Hb 100/70, BP 140/90 & 160/110);
   visit timeline; "AI xulosa" panel (Phase 7); alert history; newborn section.
   Name and PINFL masked, with a "Ko'rsatish" button (logged in the audit log).
5. /visits/new?pregnancy=… — nurse form, big touch-friendly inputs, the symptoms as chips.
   LIVE RISK PREVIEW: on each change (debounced 400 ms) call /api/risk/preview and show the zone
   and the reasons BEFORE saving. After saving, show a toast with the zone and "Ogohlantirish yuborildi" if an alert was created.
6. /alerts — inbox with an SLA countdown (red when <10 min left), escalation level, "Qabul qildim" →
   modal requiring action_taken; filters open/escalated/resolved.
7. /analytics — the model card: ROC-AUC, PR-AUC, sensitivity, calibration plot, confusion matrix,
   metrics by region, top features; badge "Sintetik ma'lumotda o'qitilgan".
8. /audit — admin only, a filterable table.
9. /about — what the system does, the decision-support disclaimer, privacy principles, data sources.

Global: a "Sintetik ma'lumot (demo)" badge in the header, toast notifications, loading skeletons,
empty states, error boundary. Polling every 15s on the dashboard and alerts (or SSE if easy).

Acceptance: `npm run build` and lint pass; every page works against the running backend; the nurse
form is usable at a 390px width; screenshots of every page saved to docs/screenshots/.
```

---

## PHASE 6 — Telegram bot

```
Read CLAUDE.md. Phase 6: the Telegram bot in bot/ (aiogram 3, polling).

- /start → asks for a one-time link code; the staff user gets the code on their profile page in the
  web app ("Telegramni ulash") → links telegram_chat_id. Also /start demo_<role> in DEMO_MODE so
  judges can join in 5 seconds from a QR code shown in the pitch.
- Consumes notification_outbox every 5s. Message format (NO name/PINFL/phone):
  "🔴 QIZIL ZONA — QQR-NUK-00421
   Homiladorlik: 31 hafta · Nukus tumani
   Sabablar: Preeklampsiya shubhasi (AB 152/98, proteinuriya +2); Gemoglobin 18 g/L ga pasaygan
   Javob berish muddati: 14:32 gacha"
  Inline buttons: "✅ Qabul qildim" (asks for a one-line action_taken reply), "📋 Kartani ochish" (link
  to the web app).
- Escalation messages say "⚠️ ESKALATSIYA (2-daraja)" and who missed the SLA.
- If TELEGRAM_BOT_TOKEN is empty, the bot service logs messages to the console instead
  (the demo never crashes).
- /mening_ogohlantirishlarim lists open alerts for this user.

Acceptance: end-to-end — save a red visit in the web app → the Telegram message arrives in <10s →
pressing "Qabul qildim" + reply updates the alert in the web app.
```

---

## PHASE 7 — LLM "AI xulosa" (safe, constrained, with a fallback)

```
Read CLAUDE.md. Phase 7: the LLM clinical summary in backend/app/llm/.

- Input to the LLM: ONLY de-identified data — patient code, age, gestational weeks, obstetric history
  flags, the last 3 visits' vitals, deltas, zone, rule_hits, trend_hits, shap_top. Never name/PINFL/phone/address.
  Add a unit test asserting that no PII fields can reach the prompt.
- An ACTION CATALOG (backend/app/llm/actions.py) of ~20 allowed, protocol-style actions in Uzbek,
  each with a code, e.g.:
  A01 "Perinatal markazga shoshilinch yo'llash", A02 "24 soat ichida arterial bosimni qayta o'lchash",
  A03 "Siydikda oqsil tahlilini takrorlash", A04 "Gemoglobin tahlilini 7 kun ichida takrorlash",
  A05 "Temir preparatlari bo'yicha shifokor ko'rigi", A06 "Homila holatini UTT/KTG bilan tekshirish",
  A07 "Patronaj tashrifini 3 kun ichida o'tkazish", A08 "Endokrinolog konsultatsiyasi", …
  The model may ONLY choose actions by code from this catalog (validated after the call). This prevents
  hallucinated treatments.
- Output JSON (validated with Pydantic): summary_uz (3–4 sentences, plain Uzbek),
  key_concerns[] (each tied to a rule/trend/feature code), recommended_action_codes[],
  questions_to_ask_patient_uz[], disclaimer_uz (fixed text: "Bu tavsiya qaror qabul qilishda
  yordam uchun. Yakuniy qarorni shifokor qabul qiladi.").
- The system prompt: the role of an obstetric decision-support assistant, Uzbek Latin script only,
  no diagnosis, no drug dosages, only catalog actions, cite the codes.
- Call the Anthropic SDK with model=LLM_MODEL, a timeout of 15s, a JSON-only response; cache the result per
  risk_assessment_id; log the token use.
- FALLBACK: if there's no key, or a timeout or invalid JSON → a deterministic template summary built from
  rule_hits/trend_hits/shap_top + a rule→action mapping table. The UI shows a small tag
  "AI (Gemini)" or "Shablon" so we are honest about which was used.
- Endpoint GET /api/llm/summary/{pregnancy_id}; the frontend panel on the patient card with a
  "Qayta yaratish" button.

Acceptance: tests for PII stripping, catalog validation (an invented action code is dropped),
and the fallback path; the patient card shows a good summary for the demo patients.
```

---

## PHASE 8 — Impact & business screens (for the business + domain judges)

```
Read CLAUDE.md. Phase 8: make the impact visible inside the product.

1. "Ta'sir" (Impact) panel on the admin dashboard, computed from the DB (synthetic):
   - median time from deterioration to specialist acknowledgement (with OnaRadar), vs a
     configurable "baseline without the system" value labelled "taxminiy" (assumption);
   - number of RED cases caught by trend rules or ML BEFORE any hard red-flag rule fired
     ("erta aniqlangan holatlar") — this is our key innovation metric;
   - SLA compliance % by district (a ranking, gamified: best/worst districts).
2. District workload forecast: a simple, explainable forecast of how many pregnancies will be
   in RED/YELLOW next month per district (based on gestational weeks + current risk), so the
   region can plan beds and specialists. Show the method in a tooltip.
3. docs/PITCH_FACTS.md: create it with placeholders that the team fills in with sourced
   real statistics (do NOT invent numbers): births per year, infant deaths, maternal mortality by
   region, the number of perinatal centres, DMED coverage. Each line: value, source, date.

Acceptance: the impact panel renders with sensible numbers; every assumption is labelled.
```

---

## PHASE 9 — Demo scenario, polish, reliability

```
Read CLAUDE.md. Phase 9: make the 3-minute live demo bulletproof.

1. Seed 3 scripted demo patients in Nukus tumani (Qoraqalpog'iston) with full visit histories:
   - QQR-NUK-DEMO1 "Dilnoza", 19 y, 1st pregnancy, now 31 weeks: BP slowly rising over the last 3 visits
     (118/76 → 128/82 → 136/88), Hb falling (118 → 104), currently YELLOW from trends + ML.
     In the live demo the nurse enters a new visit: BP 152/98, proteinuria +2, headache →
     the live preview turns RED → save → Telegram alert on the judge's phone → the specialist acknowledges.
   - QQR-NUK-DEMO2: 37 y, previous caesarean, GDM glucose 5.6 → stable YELLOW (shows explainability).
   - QQR-NUK-DEMO3: a healthy GREEN pregnancy (shows the system doesn't over-alarm).
   - One newborn with low birth weight and a danger sign → newborn RED.
2. `make demo-reset`: restores the demo state in <10s (so we can rehearse many times).
3. DEMO_MODE: SLA 2 minutes so escalation can be shown live if needed; a demo banner.
4. Performance: dashboard <1s on seeded data; add the DB indexes needed.
5. Reliability: health checks in docker compose, restart policies, graceful LLM/Telegram fallbacks,
   a frontend error boundary, no console errors.
6. Write docs/DEMO_SCRIPT.md: a minute-by-minute script with exact clicks and the lines to say in Uzbek.
7. Write a README.md: one-paragraph pitch, architecture diagram (Mermaid), screenshots, a
   "Run in 1 command" section, tech stack, team, license.
8. GitHub Actions CI: backend tests + ruff, frontend build + eslint, as badges in the README.

Acceptance: a fresh clone → `cp .env.example .env && docker compose up --build && make seed && make train`
→ the demo works start to finish; run the full demo script twice without errors.
```

---

## PHASE 10 — Teach the team + Q&A prep (for T4 "team knowledge")

```
Read the whole repo. Phase 10: help the team defend the project in front of judges.

1. docs/ARCHITECTURE.md: components, the data flow of one visit end to end, why each technology
   was chosen (1–2 lines each), scaling plan (multi-region, DMED integration, on-prem hosting in
   Uzbekistan), security model.
2. docs/PRIVACY_AND_LEGAL.md: how we follow the Law "On Personal Data" (ZRU-547), medical secrecy
   (Law on Protection of Citizens' Health), consent, encryption, role-based access, audit log,
   pseudonymisation, de-identified LLM calls, data stays on servers in Uzbekistan (recommended
   for health data even where not strictly required), decision-support positioning.
   Mark anything uncertain as "yurist bilan tasdiqlash kerak" (to confirm with a lawyer).
3. docs/QA_PREP.md: the 30 hardest questions judges may ask (technical, business, medical, legal) with
   short, honest answers. Include: "Your data is synthetic — how do you know it works?",
   "What if the model misses a case?", "Who pays?", "How is this different from DMED?",
   "Who is responsible for a wrong alert?", "How do you get real data?", "What about villages
   without internet?".
4. For each module, a 5-line "explain it like I'm presenting" summary so each team member can own one
   module: risk engine, ML, API/alerts, frontend, bot, LLM.
```

---

## PHASE 11 — Stretch (only if everything above is done and stable)

```
Pick in this order, one at a time, and stop if anything is unstable:
1. Offline nurse mode: make /visits/new a PWA; save visits to IndexedDB when offline and sync
   when back online, with conflict-safe idempotency keys. (Strong point for rural areas.)
2. Voice input for the nurse notes (Web Speech API, uz-UZ if available), with a manual fallback.
3. A SMS fallback adapter (interface + console mock) for specialists without Telegram.
4. A patient-facing Telegram reminder ("Ertaga patronaj tashrifi") — opt-in, no medical details in the text.
```

---

## Prompts for fixing things (keep handy)

- **Bug:** "Acceptance item `<…>` fails. Error: `<paste>`. Find the root cause, fix it, add a regression test, and re-run all tests."
- **UI polish:** "Review every page as a strict UX designer: spacing, alignment, Uzbek wording, empty states, mobile at 390px. List the problems, then fix them."
- **Before the pitch:** "Run the whole DEMO_SCRIPT.md end to end yourself (API calls + Playwright for the UI if available) and report anything that could fail live."
## Prototype mode (current)
Use SQLite (DATABASE_URL=sqlite:///./onaradar.db) and run without Docker until told otherwise.