"""Clinical rules (antenatal). Each hit: {code, zone, uz_text}. See docs/CLINICAL_RULES.md.

Yellow rules come in two tiers:
- Tier A (zone "yellow"): each one alone makes the pregnancy YELLOW.
- Tier B risk factors (zone "factor"): shown in grey for follow-up and used by the ML model; they make
  the pregnancy YELLOW only in combination (see `combine_factors`).
"""
from app.risk import thresholds as T
from app.risk.features import age_years, as_date, bmi, visit_weeks

ZONE_ORDER = {"green": 0, "yellow": 1, "red": 2}
FACTOR = "factor"  # Tier B risk factor: informational on its own


def max_zone(*zones: str) -> str:
    return max(zones, key=lambda z: ZONE_ORDER[z]) if zones else "green"


def _hit(code: str, zone: str, text: str) -> dict:
    return {"code": code, "zone": zone, "uz_text": text}


def _yhit(code: str, text: str) -> dict:
    """Yellow-rule hit; the tier (yellow vs factor) comes from thresholds.TIER_B_RULES."""
    return _hit(code, FACTOR if code in T.TIER_B_RULES else "yellow", text)


def _bp(v: dict) -> tuple[int | None, int | None]:
    return v.get("systolic"), v.get("diastolic")


def _is_htn(sys_: int | None, dia: int | None) -> bool:
    return (sys_ is not None and sys_ >= T.HTN_SYS) or (dia is not None and dia >= T.HTN_DIA)


def red_rules(preg: dict, visit: dict) -> list[dict]:
    hits: list[dict] = []
    gw = visit_weeks(preg, visit)
    s, d = _bp(visit)
    bp_txt = f"AB {s or '—'}/{d or '—'}"
    prot = T.PROTEINURIA_LEVELS.get(visit.get("proteinuria") or "", -1)
    syms = set(visit.get("symptoms") or [])
    hb = visit.get("hemoglobin_g_l")
    fhr = visit.get("fetal_heart_rate")
    temp = visit.get("temperature_c")
    glu = visit.get("fasting_glucose_mmol")

    if (s is not None and s >= T.SEVERE_SYS) or (d is not None and d >= T.SEVERE_DIA):
        hits.append(_hit("R01", "red", f"Og'ir gipertenziya ({bp_txt})"))
    if _is_htn(s, d) and prot >= T.PROTEINURIA_POSITIVE:
        hits.append(_hit("R02", "red", f"Preeklampsiya shubhasi ({bp_txt}, proteinuriya {visit['proteinuria']})"))
    if hb is not None and hb < T.HB_SEVERE:
        hits.append(_hit("R03", "red", f"Og'ir anemiya (gemoglobin {hb:g} g/L)"))
    if "bleeding" in syms and gw >= T.BLEEDING_MIN_WEEKS:
        hits.append(_hit("R04", "red", f"{gw:g} haftada qindan qon ketishi"))
    danger = []
    if "seizures" in syms:
        danger.append("talvasa")
    if {"severe_headache", "visual_disturbance"} <= syms:
        danger.append("kuchli bosh og'rig'i va ko'rish buzilishi")
    if "epigastric_pain" in syms and _is_htn(s, d):
        danger.append(f"epigastral og'riq va yuqori bosim ({bp_txt})")
    if "dyspnea" in syms:
        danger.append("hansirash")
    if danger:
        hits.append(_hit("R05", "red", "Xavfli belgilar: " + ", ".join(danger)))
    if fhr is not None and gw >= T.FHR_MIN_WEEKS and (fhr < T.FHR_LOW or fhr > T.FHR_HIGH):
        hits.append(_hit("R06", "red", f"Homila yurak urishi me'yordan tashqari ({fhr} zarba/daq)"))
    if "reduced_fetal_movement" in syms and gw >= T.FETAL_MOVEMENT_MIN_WEEKS:
        hits.append(_hit("R07", "red", "Homila harakati kamaygan yoki sezilmayapti"))
    if temp is not None and temp >= T.FEVER_C:
        hits.append(_hit("R08", "red", f"Yuqori harorat ({temp:g}°C)"))
    if syms & {"contractions", "membrane_rupture"} and gw < T.TERM_WEEKS:
        hits.append(_hit("R09", "red", f"Muddatidan oldin tug'ruq xavfi ({gw:g} hafta)"))
    if glu is not None and glu >= T.GLUCOSE_OVERT:
        hits.append(_hit("R10", "red", f"Och qoringa glyukoza yuqori ({glu:g} mmol/L)"))
    return hits


def yellow_rules(preg: dict, visit: dict, prev_visit: dict | None = None) -> list[dict]:
    hits: list[dict] = []
    vdate = as_date(visit["visit_date"])
    gw = visit_weeks(preg, visit)
    age = age_years(as_date(preg["birth_date"]), vdate)
    s, d = _bp(visit)
    prot = T.PROTEINURIA_LEVELS.get(visit.get("proteinuria") or "", -1)
    hb = visit.get("hemoglobin_g_l")
    glu = visit.get("fasting_glucose_mmol")
    b = bmi(preg)

    if age < T.AGE_YOUNG or age >= T.AGE_OLD:
        hits.append(_yhit("Y01", f"Onaning yoshi xavf guruhida ({int(age)} yosh)"))
    if preg.get("parity", 0) >= T.GRAND_MULTIPARA:
        hits.append(_yhit("Y02", f"Ko'p tug'ruq ({preg['parity']} marta)"))
    if preg.get("previous_cs"):
        hits.append(_yhit("Y03", "Oldingi kesarcha kesish"))
    hist = []
    if preg.get("hist_stillbirth"):
        hist.append("o'lik tug'ilish")
    if preg.get("hist_preterm"):
        hist.append("muddatidan oldin tug'ruq")
    if preg.get("miscarriages_count", 0) >= T.MISCARRIAGES_SIGNIFICANT:
        hist.append(f"{preg['miscarriages_count']} marta homila tushishi")
    if preg.get("hist_preeclampsia"):
        hist.append("preeklampsiya")
    if preg.get("hist_pph"):
        hist.append("tug'ruqdan keyingi qon ketish")
    if hist:
        hits.append(_yhit("Y04", "Akusherlik anamnezi: " + ", ".join(hist)))
    severe = (s is not None and s >= T.SEVERE_SYS) or (d is not None and d >= T.SEVERE_DIA)
    if _is_htn(s, d) and not severe and prot < T.PROTEINURIA_POSITIVE:
        hits.append(_yhit("Y05", f"Arterial bosim oshgan (AB {s}/{d}), proteinuriyasiz"))
    if hb is not None and T.HB_SEVERE <= hb < T.HB_MODERATE:
        hits.append(_yhit("Y06", f"O'rta og'ir anemiya (gemoglobin {hb:g} g/L)"))
    if glu is not None and T.GLUCOSE_GDM <= glu < T.GLUCOSE_OVERT:
        hits.append(_yhit("Y07", f"Gestatsion diabet shubhasi (glyukoza {glu:g} mmol/L)"))
    if b == b and (b < T.BMI_LOW or b >= T.BMI_HIGH):
        hits.append(_yhit("Y08", f"Tana massasi indeksi me'yordan tashqari (TMI {b:g})"))
    if preg.get("multiple_pregnancy"):
        hits.append(_yhit("Y09", "Ko'p homilali homiladorlik"))
    chronic_names = {
        "diabetes": "qandli diabet", "chronic_htn": "surunkali gipertenziya", "heart": "yurak kasalligi",
        "kidney": "buyrak kasalligi", "thyroid": "qalqonsimon bez kasalligi", "epilepsy": "epilepsiya",
    }
    chronic = [n for k, n in chronic_names.items() if preg.get(k)]
    if chronic:
        hits.append(_yhit("Y10", "Surunkali kasallik: " + ", ".join(chronic)))
    ipm = preg.get("interpregnancy_months")
    if ipm is not None and ipm < T.SHORT_INTERPREGNANCY_MONTHS:
        hits.append(_yhit("Y11", f"Homiladorliklar orasidagi qisqa interval ({ipm} oy)"))
    if preg.get("rh_negative"):
        hits.append(_yhit("Y12", "Rezus-manfiy qon guruhi"))
    booking_w = visit_weeks(preg, {"visit_date": preg["booking_date"]})
    overdue_txt = None
    if prev_visit is not None:
        gap = (vdate - as_date(prev_visit["visit_date"])).days
        limit = T.OVERDUE_DAYS_3RD_TRIMESTER if gw >= T.THIRD_TRIMESTER_WEEKS else T.OVERDUE_DAYS_OTHER
        if gap > limit:
            overdue_txt = f"tashriflar orasida {gap} kun"
    if booking_w > T.LATE_BOOKING_WEEKS or overdue_txt:
        parts = ([f"kech ro'yxatga olingan ({booking_w:g} hafta)"] if booking_w > T.LATE_BOOKING_WEEKS else [])
        parts += [overdue_txt] if overdue_txt else []
        hits.append(_yhit("Y13", "Kuzatuv uzilishi: " + ", ".join(parts)))
    if gw >= T.POSTTERM_WEEKS:
        hits.append(_yhit("Y14", f"Muddatidan o'tgan homiladorlik ({gw:g} hafta)"))
    dist = preg.get("distance_to_perinatal_km") or 0
    if dist > T.FAR_FROM_PERINATAL_KM:
        hits.append(_yhit("Y15", f"Perinatal markazdan uzoq ({dist:.0f} km)"))
    return hits


def combine_factors(rule_hits: list[dict], trend_hits: list[dict]) -> list[dict]:
    """Tier B factors raise the zone to YELLOW only as 2+ factors together, or 1 factor + any trend hit.

    Returns `rule_hits` plus a Y16 hit (zone yellow) naming the combination when it applies.
    """
    factors = [h for h in rule_hits if h["zone"] == FACTOR]
    n_needed = 1 if trend_hits else T.TIER_B_MIN_FOR_YELLOW
    if len(factors) < n_needed:
        return rule_hits
    why = ", ".join(h["code"] for h in factors) + (" + dinamika" if trend_hits and len(factors) < 2 else "")
    return rule_hits + [_hit("Y16", "yellow", f"Bir nechta xavf omili birga ({why})")]


def visit_notes(preg: dict, visit: dict) -> list[str]:
    """Informational notes that do not change the zone."""
    notes = []
    hb = visit.get("hemoglobin_g_l")
    if hb is not None and T.HB_MODERATE <= hb < T.HB_MILD:
        notes.append(f"Yengil anemiya (gemoglobin {hb:g} g/L) — kuzatib boring")
    return notes
