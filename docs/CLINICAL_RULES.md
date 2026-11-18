# OnaRadar — clinical rules

> **STATUS: to be verified by a clinician.** These rules are a decision-support prototype, not a
> diagnosis. All thresholds live in `backend/app/risk/thresholds.py` (single source of truth).

**Sources (general):** WHO recommendations on antenatal care for a positive pregnancy experience (2016);
WHO haemoglobin concentrations for the diagnosis of anaemia (2011); WHO IMCI — management of the sick
young infant; standard obstetric definitions (hypertension ≥140/90, severe ≥160/110; GDM fasting
glucose 5.1–6.9 mmol/L, overt ≥7.0 — WHO 2013 hyperglycaemia in pregnancy criteria).

Final zone = max(rule zone, trend zone, ML zone). **The ML model can only raise a zone.**

## A. Antenatal — RED (any one → RED)

| Code | Rule | Uzbek text (UI) |
|---|---|---|
| R01 | systolic ≥160 or diastolic ≥110 | Og'ir gipertenziya (AB …) |
| R02 | (systolic ≥140 or diastolic ≥90) AND proteinuria ≥ +1 | Preeklampsiya shubhasi |
| R03 | hemoglobin <70 g/L | Og'ir anemiya |
| R04 | vaginal bleeding at ≥20 weeks | … haftada qindan qon ketishi |
| R05 | seizures, OR severe headache + visual disturbance, OR epigastric pain + BP ≥140/90, OR dyspnea | Xavfli belgilar: … |
| R06 | fetal heart rate <110 or >160 bpm at ≥20 weeks | Homila yurak urishi me'yordan tashqari |
| R07 | reduced/absent fetal movement at ≥28 weeks | Homila harakati kamaygan |
| R08 | temperature ≥38.0 °C | Yuqori harorat |
| R09 | contractions or membrane rupture before 37 weeks | Muddatidan oldin tug'ruq xavfi |
| R10 | fasting glucose ≥7.0 mmol/L | Och qoringa glyukoza yuqori |

## B. Antenatal — YELLOW

Two tiers (configured in `backend/app/risk/thresholds.py`, `TIER_B_RULES`):

- **Tier A** — Y02, Y03, Y04, Y05, Y06, Y07, Y09, Y10, Y14: **each one alone → YELLOW**.
- **Tier B risk factors** — Y01, Y08, Y11, Y12, Y13, Y15: shown on the patient card in grey under
  "Xavf omillari (kuzatuv uchun)" and used by the ML model, but **alone they do not change the zone**.
  They give YELLOW only as **Y16** = 2+ Tier B factors together, OR 1 Tier B factor + any trend hit (section C).

| Code | Rule | Uzbek text |
|---|---|---|
| Y01 | age <18 or ≥35 | Onaning yoshi xavf guruhida |
| Y02 | parity ≥5 | Ko'p tug'ruq |
| Y03 | previous caesarean | Oldingi kesarcha kesish |
| Y04 | stillbirth, preterm birth, ≥2 miscarriages, previous preeclampsia or PPH | Akusherlik anamnezi: … |
| Y05 | systolic 140–159 or diastolic 90–109, proteinuria < +1 | Arterial bosim oshgan, proteinuriyasiz |
| Y06 | hemoglobin 70–99 g/L | O'rta og'ir anemiya |
| Y07 | fasting glucose 5.1–6.9 mmol/L | Gestatsion diabet shubhasi |
| Y08 | booking BMI <18.5 or ≥30 | Tana massasi indeksi me'yordan tashqari |
| Y09 | multiple pregnancy | Ko'p homilali homiladorlik |
| Y10 | any chronic disease flag | Surunkali kasallik: … |
| Y11 | interpregnancy interval <24 months | Homiladorliklar orasidagi qisqa interval |
| Y12 | Rh-negative | Rezus-manfiy qon guruhi |
| Y13 | booking >12 weeks, or gap since previous visit >30 days (≥28 weeks) / >45 days (otherwise) | Kuzatuv uzilishi |
| Y14 | ≥41 weeks, not delivered | Muddatidan o'tgan homiladorlik |
| Y15 | distance to perinatal centre >50 km | Perinatal markazdan uzoq |
| Y16 | ≥2 Tier B factors, or 1 Tier B factor + any trend hit → YELLOW | Bir nechta xavf omili birga (…) |

Note (no zone change): hemoglobin 100–109 g/L → "Yengil anemiya — kuzatib boring".

## C. Trend rules (vs previous visit; each → ≥YELLOW, two or more → RED)

| Code | Rule |
|---|---|
| T01 | hemoglobin dropped ≥15 g/L |
| T02 | systolic rose ≥20 or diastolic rose ≥15 mmHg |
| T03 | weight gain >1.0 kg/week after 20 weeks (sudden edema) |
| T04 | fundal height ≥3 cm below gestational weeks after 24 weeks (FGR suspicion) |
| T05 | ML probability rose by ≥0.15 since the previous assessment |

### C2. Predictive trend rules P01–P05 (last 3 visits of the same pregnancy)

Goal: flag a value moving **steadily** in a dangerous direction before any single value crosses a static
threshold. Slopes are per gestational week (value change ÷ weeks between visits), so uneven visit spacing is
handled; the projection is linear, `PRED_HORIZON_WEEKS` (2) ahead. Steps shorter than 0.5 week → rule skipped.
With fewer than 3 visits only T01–T05 run. A P-rule replaces the T-rule of the same signal
(P01>T02, P02>T01, P03>T03, P04>T04, P05>T05) so one change is never counted twice. Each hit carries
`kind: "trend"`, the 3 values, gestational weeks and dates (shown as a sparkline in the UI).

| Code | Rule | Zone |
|---|---|---|
| P01 | systolic or diastolic rising at every step (from 20 weeks) AND projected ≥140 / ≥90 | YELLOW; RED if already ≥130 systolic or ≥85 diastolic now |
| P02 | hemoglobin falling at every step AND projected <100 g/L | YELLOW |
| P03 | weight gain >1.0 kg/week at BOTH steps (from 20 weeks) — oedema / pre-eclampsia sign | YELLOW |
| P04 | fundal-height lag behind gestational weeks growing at each step and ≥2 cm now (from 24 weeks) | YELLOW |
| P05 | ML probability rising at each step, total rise ≥0.15 | YELLOW |

Combination: 2+ trend hits, any red trend hit, or **a P-hit together with a Tier A clinical yellow rule**
(Y16 factor combinations do not count) → **RED**. Example text: "Sistolik bosim 3 ko'rikda ketma-ket
oshmoqda: 118 → 126 → 134; shu sur'atda 2 haftada 140 dan oshishi mumkin". Thresholds and their rationale:
`thresholds.py` (`PRED_*`).

## D. Newborn (WHO IMCI young-infant danger signs)

| Code | Zone | Rule |
|---|---|---|
| N01 | RED | not feeding well |
| N02 | RED | convulsions |
| N03 | RED | respiratory rate ≥60/min |
| N04 | RED | severe chest indrawing |
| N05 | RED | temperature ≥37.5 °C or <35.5 °C |
| N06 | RED | movement only when stimulated |
| N07 | RED | jaundice in the first 24 h or on palms/soles |
| N08 | RED | birth weight <1500 g |
| N09 | YELLOW | birth weight 1500–2499 g |
| N10 | YELLOW | preterm <37 weeks |
| N11 | YELLOW | Apgar (5 min) <7 |
| N12 | YELLOW | mother was RED in the 3rd trimester |
| N13 | YELLOW | no postnatal check by day 3 |

N01–N13 apply **from day 0 to day 28** (`NEONATAL_DAYS`). After that the infant rules below take over.

## D2. Children 0–12 months ("Bola") — `backend/app/risk/infant.py`

A child is followed until the 1st birthday (`status` active → graduated). **No ML model for children:** zone =
max(rule zone, growth-trend zone), and the explanation says "Bolalar uchun faqat klinik qoidalar va trendlar".
Sources: WHO IMCI chart booklet (2014): "sick young infant up to 2 months" and "sick child 2 months to 5 years"
danger signs; WHO Child Growth Standards (2006), weight-for-age; the national immunisation calendar of Uzbekistan
(first-year doses). All thresholds are in `thresholds.py` (`INF_*`, `WFA_TABLE`, `VACCINE_SCHEDULE`).
**Status: must be verified by a clinician before any real use.**

| Code | Zone | Rule (age) |
|---|---|---|
| I01 | RED | not able to feed / breastfeed (day 29+; N01 before) |
| I02 | RED | vomits everything (any age) |
| I03 | RED | convulsions (day 29+; N02 before) |
| I04 | RED | lethargic / unconscious, or moves only when stimulated (day 29+; `lethargic` at any age) |
| I05 | RED | fast breathing **for age**: ≥ 60/min under 2 months, ≥ 50/min from 2 to 12 months (day 29+; N03 before) |
| I06 | RED | severe chest indrawing (day 29+; N04 before) |
| I07 | RED | temperature ≥ 38.0 °C under 2 months, or < 35.5 °C (day 29+; N05 before) |
| I08 | RED | blood in stool |
| I09 | RED | diarrhoea ≥ 14 days |
| I10 | YELLOW | weight-for-age below −2 SD (WHO table for the child's sex) |
| I11 | YELLOW | a scheduled vaccine dose more than 30 days overdue |
| I12 | YELLOW | cough ≥ 14 days |
| I13 | YELLOW | no check for more than 30 days (monthly checks in the first year; day 29+) |
| I14 | YELLOW | not exclusively breastfed before 6 months (mixed, formula or complementary food) |

**Weight-for-age z-score.** `WFA_TABLE` holds the WHO median and −2 SD weight (kg) for each completed month
0–12, boys and girls (WHO simplified field tables). z = (weight − median) / SD with SD = (median − (−2 SD)) / 2,
linear between months. This approximates the WHO LMS method on the lower half of the distribution, which is
where the rules act.

**Vaccines.** Only dose names and due ages are stored (`VACCINE_SCHEDULE`: HepB-0 day 0; BCG, OPV-0 day 3;
Penta-1, OPV-1, Rota-1, PCV-1 at 2 months; the 2nd doses at 3 months; Penta-3, OPV-3, IPV-1 at 4 months; MMR-1,
PCV-3 at 12 months). Due dates are computed from the birth date. Doses given are recorded per check
(`vaccines_given`), and the overdue list on that day is stored in `vaccines_due_overdue`.

### Growth trends (last checks, ≥ 7 days apart)

| Code | Zone | Rule |
|---|---|---|
| G01 | ≥ YELLOW | weight-for-age z fell by ≥ 0.67 since the previous check (≈ crossing two percentile lines) |
| G02 | ≥ YELLOW | weight not increasing at 2 consecutive checks ("o'sish to'xtashi") |

Combination (same idea as task 07): a growth trend **plus any yellow rule**, or both G01 and G02 → **RED**.

## E. ML thresholds
`ML_YELLOW` / `ML_RED` are written by `backend/ml/train.py`, chosen on a held-out calibration split so that
the combined system (rules + trends OR ML ≥ yellow) flags ≥85% of pregnancies with an adverse outcome
as YELLOW/RED at least once from 28 weeks (pregnancy-level sensitivity). Per-visit sensitivity is
reported next to it. See
`backend/ml/MODEL_CARD.md` and `backend/ml/artifacts/metrics.json`.

## F. Adaptive visit intensity (advisory only; mandatory 12 visits are NEVER reduced)
All thresholds live in `backend/app/risk/thresholds.py` (`STANDARD_VISITS = 12`, `CONSECUTIVE_GREEN_REQUIRED = 3`,
`LIGHT_VISIT_MAX_WEEKS = 36`, `MINUTES_SAVED_PER_LIGHT_VISIT = 10`).

- **National 12-visit standard is strictly respected**: Every pregnancy schedule always contains all **12 mandatory
  antenatal visits** (`STANDARD_VISIT_WEEKS = (8, 12, 16, 20, 24, 28, 30, 32, 34, 36, 38, 40)`). The system **never**
  recommends fewer than 12 visits.
- **Visit intensity**: Each scheduled visit has an intensity of either `"To'liq"` (full doctor visit) or `"Yengil"`
  (light visit: nurse-led standard checks only).
- **Eligibility for `"Yengil"`**:
  1. At least `CONSECUTIVE_GREEN_REQUIRED = 3` consecutive green assessments,
  2. No Tier B risk factor (`Y01, Y08, Y11, Y12, Y13, Y15`) or Tier A / red rule hit,
  3. No trend hit (`T01–T05`, `P01–P05`),
  4. No open or escalated alert,
  5. Current gestational age `< LIGHT_VISIT_MAX_WEEKS` (36 weeks); from 36 weeks onwards all visits stay `"To'liq"`.
- **Immediate safety reset**: Any yellow or red result, or any new risk factor, returns **all** remaining visits to
  `"To'liq"` immediately (`reset_visit_intensity` in `AuditLog`).
- **Doctor-only confirmation & Clinical/Ministry approval**: The recommendation (`"Tavsiya: yengil ko'rik (oxirgi N ta natija yashil)"`)
  is advisory only and is **never applied automatically**. Only the `doctor` role can confirm it (`confirm_light_visit`),
  and every recommendation and confirmation is audit-logged. Any real-world change to visit intensity requires clinical
  validation and formal approval by the Ministry of Health (SSV).
- **Vazirlikka taklif (`PROPOSE_FEWER_VISITS=false`, OFF by default, docs-only)**: As a policy proposal for future
  consideration by the Ministry of Health, a pilot study could evaluate whether a reduced visit count is safe for
  persistently low-risk pregnancies if formally approved by the Ministry. There is no UI button for reducing visit
  counts, and OnaRadar always enforces the full 12-visit schedule.
