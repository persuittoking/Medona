"""Feature building shared by training (synthetic data) and live scoring.

Inputs are plain dicts so the same code runs on DB rows, API payloads and the generator.
pregnancy: keys of models.Pregnancy + 'birth_date' + 'distance_to_perinatal_km'.
visits: chronological list of visit dicts; the LAST one is the visit being scored.
"""
from datetime import date
from math import nan

from app.risk import thresholds as T

SYMPTOMS = [
    "bleeding", "severe_headache", "visual_disturbance", "epigastric_pain", "seizures",
    "dyspnea", "reduced_fetal_movement", "contractions", "membrane_rupture", "edema",
]

FEATURES = [
    "age", "gest_weeks", "booking_weeks", "gravidity", "parity", "previous_cs",
    "hist_stillbirth", "hist_preterm", "miscarriages_count", "hist_preeclampsia", "hist_pph",
    "diabetes", "chronic_htn", "other_chronic", "multiple_pregnancy", "rh_negative",
    "interpregnancy_months", "bmi_booking", "distance_km",
    "systolic", "diastolic", "proteinuria_level", "hemoglobin", "glucose", "temperature",
    "fetal_heart_rate", "fundal_gap", "weight_gain_rate",
    "d_systolic", "d_diastolic", "d_hemoglobin", "max_systolic", "min_hemoglobin",
    "symptom_count", "danger_symptom", "n_visits",
]

DANGER_SYMPTOMS = {"bleeding", "severe_headache", "visual_disturbance", "epigastric_pain", "seizures", "dyspnea"}


def as_date(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v))


def age_years(birth: date, on: date) -> float:
    return (on - birth).days / 365.25


def gest_weeks(lmp: date, on: date) -> float:
    return round((on - lmp).days / 7.0, 1)


def bmi(preg: dict) -> float:
    h = (preg.get("height_cm") or 0) / 100
    w = preg.get("booking_weight_kg")
    return round(w / (h * h), 1) if h and w else nan


def protein_level(v: str | None) -> float:
    return float(T.PROTEINURIA_LEVELS.get(v, nan)) if v else nan


def _num(v) -> float:
    return nan if v is None else float(v)


def _delta(cur, prev) -> float:
    return nan if cur is None or prev is None else float(cur) - float(prev)


def visit_weeks(preg: dict, visit: dict) -> float:
    if visit.get("gestational_weeks") is not None:
        return float(visit["gestational_weeks"])
    return gest_weeks(as_date(preg["lmp_date"]), as_date(visit["visit_date"]))


def weight_gain_rate(preg: dict, visits: list[dict]) -> float:
    """kg/week between the previous and current visit (nan if not computable)."""
    if len(visits) < 2:
        return nan
    cur, prev = visits[-1], visits[-2]
    if cur.get("weight_kg") is None or prev.get("weight_kg") is None:
        return nan
    dw = visit_weeks(preg, cur) - visit_weeks(preg, prev)
    return round((cur["weight_kg"] - prev["weight_kg"]) / dw, 2) if dw > 0.5 else nan


def build_features(preg: dict, visits: list[dict]) -> dict[str, float]:
    cur = visits[-1]
    prev = visits[-2] if len(visits) > 1 else {}
    vdate = as_date(cur["visit_date"])
    gw = visit_weeks(preg, cur)
    booking_w = gest_weeks(as_date(preg["lmp_date"]), as_date(preg["booking_date"]))
    fundal = cur.get("fundal_height_cm")
    syms = set(cur.get("symptoms") or [])
    sys_hist = [v["systolic"] for v in visits if v.get("systolic") is not None]
    hb_hist = [v["hemoglobin_g_l"] for v in visits if v.get("hemoglobin_g_l") is not None]
    ipm = preg.get("interpregnancy_months")
    return {
        "age": round(age_years(as_date(preg["birth_date"]), vdate), 1),
        "gest_weeks": gw,
        "booking_weeks": booking_w,
        "gravidity": float(preg.get("gravidity", 1)),
        "parity": float(preg.get("parity", 0)),
        "previous_cs": float(bool(preg.get("previous_cs"))),
        "hist_stillbirth": float(bool(preg.get("hist_stillbirth"))),
        "hist_preterm": float(bool(preg.get("hist_preterm"))),
        "miscarriages_count": float(preg.get("miscarriages_count", 0)),
        "hist_preeclampsia": float(bool(preg.get("hist_preeclampsia"))),
        "hist_pph": float(bool(preg.get("hist_pph"))),
        "diabetes": float(bool(preg.get("diabetes"))),
        "chronic_htn": float(bool(preg.get("chronic_htn"))),
        "other_chronic": float(any(preg.get(k) for k in ("heart", "kidney", "thyroid", "epilepsy"))),
        "multiple_pregnancy": float(bool(preg.get("multiple_pregnancy"))),
        "rh_negative": float(bool(preg.get("rh_negative"))),
        "interpregnancy_months": nan if ipm is None else float(ipm),
        "bmi_booking": bmi(preg),
        "distance_km": _num(preg.get("distance_to_perinatal_km")),
        "systolic": _num(cur.get("systolic")),
        "diastolic": _num(cur.get("diastolic")),
        "proteinuria_level": protein_level(cur.get("proteinuria")),
        "hemoglobin": _num(cur.get("hemoglobin_g_l")),
        "glucose": _num(cur.get("fasting_glucose_mmol")),
        "temperature": _num(cur.get("temperature_c")),
        "fetal_heart_rate": _num(cur.get("fetal_heart_rate")),
        "fundal_gap": round(fundal - gw, 1) if fundal is not None and gw >= 20 else nan,
        "weight_gain_rate": weight_gain_rate(preg, visits),
        "d_systolic": _delta(cur.get("systolic"), prev.get("systolic")),
        "d_diastolic": _delta(cur.get("diastolic"), prev.get("diastolic")),
        "d_hemoglobin": _delta(cur.get("hemoglobin_g_l"), prev.get("hemoglobin_g_l")),
        "max_systolic": float(max(sys_hist)) if sys_hist else nan,
        "min_hemoglobin": float(min(hb_hist)) if hb_hist else nan,
        "symptom_count": float(len(syms)),
        "danger_symptom": float(bool(syms & DANGER_SYMPTOMS)),
        "n_visits": float(len(visits)),
    }
