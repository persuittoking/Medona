"""ALL clinical thresholds live here (single source of truth).

Sources: WHO antenatal care recommendations (2016), WHO haemoglobin thresholds for anaemia,
WHO IMCI young-infant danger signs, standard obstetric definitions.
STATUS: to be verified by a clinician before any real use.
"""

# --- Blood pressure (mmHg) ---
SEVERE_SYS = 160
SEVERE_DIA = 110
HTN_SYS = 140
HTN_DIA = 90

# --- Proteinuria (dipstick) ---
PROTEINURIA_LEVELS = {"neg": 0, "trace": 1, "+1": 2, "+2": 3, "+3": 4}
PROTEINURIA_POSITIVE = 2  # ">= +1"

# --- Hemoglobin (g/L) ---
HB_SEVERE = 70
HB_MODERATE = 100   # 70-99 -> moderate anaemia (yellow)
HB_MILD = 110       # 100-109 -> mild anaemia (note only)

# --- Glucose, fasting (mmol/L) ---
GLUCOSE_OVERT = 7.0
GLUCOSE_GDM = 5.1

# --- Fetal / other ---
FHR_LOW = 110
FHR_HIGH = 160
FHR_MIN_WEEKS = 20
BLEEDING_MIN_WEEKS = 20
FETAL_MOVEMENT_MIN_WEEKS = 28
FEVER_C = 38.0
TERM_WEEKS = 37
POSTTERM_WEEKS = 41

# --- Risk factors ---
AGE_YOUNG = 18
AGE_OLD = 35
GRAND_MULTIPARA = 5
MISCARRIAGES_SIGNIFICANT = 2
BMI_LOW = 18.5
BMI_HIGH = 30.0
SHORT_INTERPREGNANCY_MONTHS = 24
LATE_BOOKING_WEEKS = 12
OVERDUE_DAYS_3RD_TRIMESTER = 30
OVERDUE_DAYS_OTHER = 45
THIRD_TRIMESTER_WEEKS = 28
FAR_FROM_PERINATAL_KM = 50

# --- Yellow-rule tiers ---
# Tier B rules are risk factors for follow-up: alone they do NOT change the zone.
# YELLOW when >= TIER_B_MIN_FOR_YELLOW factors coincide, or 1 factor + any trend hit.
TIER_B_RULES = ("Y01", "Y08", "Y11", "Y12", "Y13", "Y15")  # age, BMI, interpregnancy, Rh-, late/overdue, distance
TIER_B_MIN_FOR_YELLOW = 2

# --- Trend rules (vs previous visit) ---
TREND_HB_DROP = 15
TREND_SYS_RISE = 20
TREND_DIA_RISE = 15
TREND_WEIGHT_GAIN_KG_PER_WEEK = 1.0
TREND_WEIGHT_MIN_WEEKS = 20
TREND_FUNDAL_LAG_CM = 3
TREND_FUNDAL_MIN_WEEKS = 24
TREND_ML_RISE = 0.15

# --- Predictive trend rules P01-P05 (last PRED_MIN_VISITS visits of the same pregnancy) ---
# Slopes are per gestational WEEK (value change / weeks between visits), so uneven visit spacing is handled.
PRED_MIN_VISITS = 3            # 3 visits = 2 intervals: "rising at every step" needs two steps
PRED_HORIZON_WEEKS = 2.0       # linear projection horizon; ~ the usual 2-week 3rd-trimester visit interval
PRED_MIN_INTERVAL_WEEKS = 0.5  # gaps shorter than half a week give unstable per-week slopes -> rule skipped
PRED_BP_MIN_WEEKS = 20.0       # gestational hypertension is defined from 20 weeks (ACOG/ISSHP)
PRED_BP_RED_SYS = 130          # "high-normal" BP band 130-139 / 85-89 (ESC/ESH 2018): P01 -> RED from here
PRED_BP_RED_DIA = 85
PRED_HB_TARGET = HB_MODERATE   # P02: projected below the yellow anaemia threshold (Y06, WHO moderate < 100 g/L)
PRED_WEIGHT_GAIN_KG_PER_WEEK = TREND_WEIGHT_GAIN_KG_PER_WEEK  # P03: > 1 kg/week at BOTH steps (oedema sign)
PRED_FUNDAL_MIN_LAG_CM = 2.0   # P04: lag must grow at each step AND reach 2 cm (SFH tolerance +/-2 cm, FIGO/NICE)
PRED_ML_RISE_TOTAL = TREND_ML_RISE  # P05: ML probability rising at each step, total rise >= this

# --- Newborn (WHO IMCI young infant) ---
NB_RESP_RATE_FAST = 60
NB_TEMP_HIGH = 37.5
NB_TEMP_LOW = 35.5
NB_VLBW_G = 1500
NB_LBW_G = 2500
NB_APGAR_LOW = 7
NB_CHECK_BY_DAY = 3
NEONATAL_DAYS = 28  # N01-N13 apply up to and including day 28

# --- Infant 0-12 months (I01-I14, G01-G02) ---
# Sources: WHO IMCI chart booklet (2014) — "sick young infant up to 2 months" and "sick child 2 months to 5 years"
# danger signs; WHO Child Growth Standards (2006) weight-for-age. STATUS: to be verified by a clinician.
INFANT_MAX_DAYS = 365              # followed until the 1st birthday, then status "graduated"
YOUNG_INFANT_DAYS = 60             # "under 2 months" (IMCI young infant)
INF_RESP_FAST_UNDER_2M = 60        # IMCI fast breathing: >= 60/min under 2 months
INF_RESP_FAST_2_12M = 50           # IMCI fast breathing: >= 50/min from 2 to 12 months
INF_TEMP_HIGH_UNDER_2M = 38.0      # IMCI young infant: fever >= 38.0 °C is a danger sign
INF_TEMP_LOW = 35.5                # hypothermia < 35.5 °C
INF_DIARRHOEA_PERSISTENT_DAYS = 14  # IMCI: persistent diarrhoea >= 14 days
INF_COUGH_CHRONIC_DAYS = 14        # IMCI: cough >= 14 days -> refer for assessment (TB etc.)
INF_WFA_LOW_Z = -2.0               # WHO: weight-for-age below -2 SD = underweight
INF_VACCINE_OVERDUE_DAYS = 30      # a scheduled dose more than 30 days late
INF_CHECK_INTERVAL_DAYS = 30       # patronage / polyclinic check monthly in the first year
INF_EXCLUSIVE_BF_DAYS = 183        # WHO: exclusive breastfeeding for the first 6 months
# Growth trends over the last checks (WHO growth standards: a fall crossing 2 major percentile lines
# ~ 0.67 SD is the usual "growth faltering" signal).
INF_Z_DROP = 0.67
INF_PLATEAU_STEPS = 2              # weight not increasing at 2 consecutive checks
INF_MIN_TREND_GAP_DAYS = 7         # checks closer than a week are too noisy for growth trends

# WHO Child Growth Standards, weight-for-age 0-12 months (kg): (median, -2 SD) by completed month.
# Source: WHO simplified field tables "Weight-for-age BOYS / GIRLS, birth to 2 years (z-scores)", 2006.
# z is computed on the lower half of the distribution: SD = (median - (-2SD)) / 2, linear between months —
# an approximation of the WHO LMS method, accurate enough below the median where the rule acts.
WFA_TABLE: dict[str, list[tuple[float, float]]] = {
    "m": [(3.3, 2.5), (4.5, 3.4), (5.6, 4.3), (6.4, 5.0), (7.0, 5.6), (7.5, 6.0), (7.9, 6.4),
          (8.3, 6.7), (8.6, 6.9), (8.9, 7.1), (9.2, 7.4), (9.4, 7.6), (9.6, 7.7)],
    "f": [(3.2, 2.4), (4.2, 3.2), (5.1, 3.9), (5.8, 4.5), (6.4, 5.0), (6.9, 5.4), (7.3, 5.7),
          (7.6, 6.0), (7.9, 6.3), (8.2, 6.5), (8.5, 6.7), (8.7, 6.9), (8.9, 7.0)],
}
DAYS_PER_MONTH = 30.4375

# National immunisation calendar of Uzbekistan, first year (dose code, vaccine family, due age in days).
# Only names + ages; due dates are computed from the birth date. To be verified against the current MoH order.
VACCINE_SCHEDULE: list[tuple[str, str, int]] = [
    ("HepB-0", "HepB", 0), ("BCG", "BCG", 3), ("OPV-0", "OPV/IPV", 3),
    ("Penta-1", "Pentavalent", 61), ("OPV-1", "OPV/IPV", 61), ("Rota-1", "Rotavirus", 61), ("PCV-1", "PCV", 61),
    ("Penta-2", "Pentavalent", 91), ("OPV-2", "OPV/IPV", 91), ("Rota-2", "Rotavirus", 91), ("PCV-2", "PCV", 91),
    ("Penta-3", "Pentavalent", 122), ("OPV-3", "OPV/IPV", 122), ("IPV-1", "OPV/IPV", 122),
    ("MMR-1", "MMR", 365), ("PCV-3", "PCV", 365),
]

# --- ML probability cut-offs ---
# BEGIN ML THRESHOLDS (auto-written by backend/ml/train.py — do not edit by hand)
ML_YELLOW = 0.12
ML_RED = 0.35
ML_THRESHOLDS_NOTE = 'chosen 2026-11-17 on calibration split: pregnancy-level recall target 85% (flagged from 28 w); test pregnancy-level sensitivity 91.8%, per-visit 63.7%; model 5622c10fe7'
# END ML THRESHOLDS
