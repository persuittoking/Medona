"""Newborn rules (WHO IMCI young-infant danger signs)."""
from datetime import date

from app.risk import thresholds as T
from app.risk.rules import max_zone


def _hit(code: str, zone: str, text: str) -> dict:
    return {"code": code, "zone": zone, "uz_text": text}


def newborn_hits(newborn: dict, check: dict | None, mother_red_3rd_trimester: bool = False,
                 today: date | None = None) -> list[dict]:
    hits: list[dict] = []
    c = check or {}
    bw = newborn.get("birth_weight_g")
    if c.get("not_feeding_well"):
        hits.append(_hit("N01", "red", "Yaxshi emmayapti"))
    if c.get("convulsions"):
        hits.append(_hit("N02", "red", "Talvasa"))
    rr = c.get("resp_rate")
    if rr is not None and rr >= T.NB_RESP_RATE_FAST:
        hits.append(_hit("N03", "red", f"Tez nafas olish ({rr}/daq)"))
    if c.get("severe_chest_indrawing"):
        hits.append(_hit("N04", "red", "Ko'krak qafasining kuchli tortilishi"))
    t = c.get("temperature_c")
    if t is not None and (t >= T.NB_TEMP_HIGH or t < T.NB_TEMP_LOW):
        hits.append(_hit("N05", "red", f"Harorat me'yordan tashqari ({t:g}°C)"))
    if c.get("movement_only_when_stimulated"):
        hits.append(_hit("N06", "red", "Faqat qo'zg'atilganda harakatlanadi"))
    if c.get("jaundice_first_24h") or c.get("jaundice_palms_soles"):
        hits.append(_hit("N07", "red", "Xavfli sariqlik (birinchi 24 soatda yoki kaft/tovonda)"))
    if bw is not None and bw < T.NB_VLBW_G:
        hits.append(_hit("N08", "red", f"Juda kam tug'ilish vazni ({bw} g)"))
    if bw is not None and T.NB_VLBW_G <= bw < T.NB_LBW_G:
        hits.append(_hit("N09", "yellow", f"Kam tug'ilish vazni ({bw} g)"))
    ga = newborn.get("gestational_weeks_at_birth")
    if ga is not None and ga < T.TERM_WEEKS:
        hits.append(_hit("N10", "yellow", f"Chala tug'ilgan ({ga:g} hafta)"))
    ap = newborn.get("apgar_5")
    if ap is not None and ap < T.NB_APGAR_LOW:
        hits.append(_hit("N11", "yellow", f"Apgar (5 daq) past: {ap}"))
    if mother_red_3rd_trimester:
        hits.append(_hit("N12", "yellow", "Ona 3-trimestrda qizil zonada bo'lgan"))
    if check is None and today is not None:
        age_days = (today - newborn["birth_date"]).days
        if age_days > T.NB_CHECK_BY_DAY:
            hits.append(_hit("N13", "yellow", f"Tug'ruqdan keyingi ko'rik o'tkazilmagan ({age_days} kun)"))
    return hits


def newborn_zone(hits: list[dict]) -> str:
    return max_zone(*[h["zone"] for h in hits]) if hits else "green"
