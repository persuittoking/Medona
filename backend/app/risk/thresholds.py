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

# --- Trend rules (vs previous visit) ---
TREND_HB_DROP = 15
TREND_SYS_RISE = 20
TREND_DIA_RISE = 15
TREND_WEIGHT_GAIN_KG_PER_WEEK = 1.0
TREND_WEIGHT_MIN_WEEKS = 20
TREND_FUNDAL_LAG_CM = 3
TREND_FUNDAL_MIN_WEEKS = 24
TREND_ML_RISE = 0.15

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
ML_YELLOW = 0.115
ML_RED = 0.255
ML_THRESHOLDS_NOTE = 'chosen 2026-11-17 on calibration split: system recall target 90%; test system sensitivity 89.0%; model e07aca5c61'
# END ML THRESHOLDS
