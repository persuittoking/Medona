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

# --- ML probability cut-offs ---
# BEGIN ML THRESHOLDS (auto-written by backend/ml/train.py — do not edit by hand)
ML_YELLOW = 0.12
ML_RED = 0.35
ML_THRESHOLDS_NOTE = 'chosen 2026-11-17 on calibration split: pregnancy-level recall target 85% (flagged from 28 w); test pregnancy-level sensitivity 91.8%, per-visit 63.7%; model 5622c10fe7'
# END ML THRESHOLDS
