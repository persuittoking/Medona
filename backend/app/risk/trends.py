"""Trend rules: compare the current visit with the previous one.

Each hit raises the zone to at least YELLOW; two or more hits together -> RED.
"""
from app.risk import thresholds as T
from app.risk.features import visit_weeks, weight_gain_rate


def _hit(code: str, text: str) -> dict:
    return {"code": code, "zone": "yellow", "uz_text": text}


def trend_hits(preg: dict, visits: list[dict], ml_prob: float | None = None,
               prev_ml_prob: float | None = None) -> list[dict]:
    cur = visits[-1]
    prev = visits[-2] if len(visits) > 1 else None
    gw = visit_weeks(preg, cur)
    hits: list[dict] = []
    if prev is not None:
        hb, phb = cur.get("hemoglobin_g_l"), prev.get("hemoglobin_g_l")
        if hb is not None and phb is not None and phb - hb >= T.TREND_HB_DROP:
            hits.append(_hit("T01", f"Gemoglobin pasaygan ({phb:g} → {hb:g} g/L, −{phb - hb:g})"))
        s, ps = cur.get("systolic"), prev.get("systolic")
        d, pd = cur.get("diastolic"), prev.get("diastolic")
        sys_up = s is not None and ps is not None and s - ps >= T.TREND_SYS_RISE
        dia_up = d is not None and pd is not None and d - pd >= T.TREND_DIA_RISE
        if sys_up or dia_up:
            hits.append(_hit("T02", f"Arterial bosim keskin oshgan ({ps}/{pd} → {s}/{d})"))
        rate = weight_gain_rate(preg, visits)
        if gw >= T.TREND_WEIGHT_MIN_WEEKS and rate == rate and rate > T.TREND_WEIGHT_GAIN_KG_PER_WEEK:
            hits.append(_hit("T03", f"Vazn tez ortgan ({rate:g} kg/hafta) — shish ehtimoli"))
    fundal = cur.get("fundal_height_cm")
    if fundal is not None and gw >= T.TREND_FUNDAL_MIN_WEEKS and gw - fundal >= T.TREND_FUNDAL_LAG_CM:
        hits.append(_hit("T04", f"Bachadon tubi balandligi muddatdan orqada ({fundal:g} sm, {gw:g} hafta) — "
                                "homila o'sishi sekinlashishi shubhasi"))
    if ml_prob is not None and prev_ml_prob is not None and ml_prob - prev_ml_prob >= T.TREND_ML_RISE:
        hits.append(_hit("T05", f"Model bo'yicha xavf ehtimoli oshgan ({prev_ml_prob:.0%} → {ml_prob:.0%})"))
    return hits


def trend_zone(hits: list[dict]) -> str:
    if len(hits) >= 2:
        return "red"
    return "yellow" if hits else "green"
