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

## E. ML thresholds
`ML_YELLOW` / `ML_RED` are written by `backend/ml/train.py`, chosen on a held-out calibration split so that
the combined system (rules + trends OR ML ≥ yellow) flags ≥85% of pregnancies with an adverse outcome
as YELLOW/RED at least once from 28 weeks (pregnancy-level sensitivity). Per-visit sensitivity is
reported next to it. See
`backend/ml/MODEL_CARD.md` and `backend/ml/artifacts/metrics.json`.
