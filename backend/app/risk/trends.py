"""Trend rules.

- T01-T05 compare the current visit with the previous one (sudden change).
- P01-P05 ("predictive") look at the last PRED_MIN_VISITS visits of the same pregnancy and flag a value that
  moves steadily in a dangerous direction, using the slope per gestational week and a linear projection
  PRED_HORIZON_WEEKS ahead — even when no single value has crossed a static threshold yet.
  With fewer than PRED_MIN_VISITS visits only the T-rules run.

A P-rule supersedes the T-rule for the same signal (P01>T02, P02>T01, P03>T03, P04>T04, P05>T05), so one
physiological change is never counted twice. Zone: each hit >= YELLOW; any red hit, 2+ hits, or a P-hit
together with a clinical (Tier A) yellow rule -> RED. Texts say "xavf belgisi / shubha", never a diagnosis.
"""
from app.risk import thresholds as T
from app.risk.features import as_date, visit_weeks, weight_gain_rate

PREDICTIVE_CODES = ("P01", "P02", "P03", "P04", "P05")
SUPERSEDES = {"P01": "T02", "P02": "T01", "P03": "T03", "P04": "T04", "P05": "T05"}


def _hit(code: str, text: str, zone: str = "yellow", **series) -> dict:
    return {"code": code, "zone": zone, "uz_text": text, "kind": "trend", **series}


def _fmt(x: float) -> str:
    return f"{x:g}" if abs(x - round(x)) > 1e-9 else str(int(round(x)))


def _arrow(values: list[float]) -> str:
    return " → ".join(_fmt(v) for v in values)


def is_predictive(hit: dict) -> bool:
    return hit.get("code") in PREDICTIVE_CODES


# ---------------- T-rules: current vs previous visit ----------------
def _pair_hits(preg: dict, visits: list[dict], ml_prob: float | None, prev_ml_prob: float | None) -> list[dict]:
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


# ---------------- P-rules: last 3 visits, slope per week ----------------
def _series(preg: dict, visits: list[dict], key: str) -> tuple[list[float], list[float]] | None:
    """(values, gestational weeks) of `key` over the visits, or None if a value is missing / a gap is too short."""
    vals = [v.get(key) for v in visits]
    if any(x is None for x in vals):
        return None
    weeks = [visit_weeks(preg, v) for v in visits]
    if any(b - a < T.PRED_MIN_INTERVAL_WEEKS for a, b in zip(weeks, weeks[1:], strict=False)):
        return None
    return [float(x) for x in vals], weeks


def _monotonic(vals: list[float], up: bool) -> bool:
    steps = [b - a for a, b in zip(vals, vals[1:], strict=False)]
    return all(s > 0 for s in steps) if up else all(s < 0 for s in steps)


def slope_per_week(vals: list[float], weeks: list[float]) -> float:
    """Average change per gestational week between the first and last point."""
    return (vals[-1] - vals[0]) / (weeks[-1] - weeks[0])


def projected(vals: list[float], weeks: list[float], horizon: float = T.PRED_HORIZON_WEEKS) -> float:
    return vals[-1] + slope_per_week(vals, weeks) * horizon


def _meta(visits: list[dict], vals: list[float], weeks: list[float], direction: str, unit: str, param: str,
          proj: float | None = None) -> dict:
    return {"param": param, "values": [round(v, 2) for v in vals], "weeks": [round(w, 1) for w in weeks],
            "dates": [as_date(v["visit_date"]).isoformat() for v in visits], "direction": direction, "unit": unit,
            "projected": None if proj is None else round(proj, 1), "horizon_weeks": T.PRED_HORIZON_WEEKS}


def _p01_bp(preg: dict, last: list[dict]) -> dict | None:
    if visit_weeks(preg, last[0]) < T.PRED_BP_MIN_WEEKS:
        return None
    parts, meta = [], None
    for key, label, limit, red_from in (("systolic", "Sistolik", T.HTN_SYS, T.PRED_BP_RED_SYS),
                                        ("diastolic", "Diastolik", T.HTN_DIA, T.PRED_BP_RED_DIA)):
        ser = _series(preg, last, key)
        if ser is None or not _monotonic(ser[0], up=True):
            continue
        proj = projected(*ser)
        if proj < limit:
            continue
        red = ser[0][-1] >= red_from
        parts.append((label, ser, limit, red))
        meta = meta or _meta(last, ser[0], ser[1], "up", "mmHg", key, proj)
    if not parts:
        return None
    label, (vals, _), limit, _ = parts[0]
    text = (f"{label} bosim {len(vals)} ko'rikda ketma-ket oshmoqda: {_arrow(vals)}; shu sur'atda "
            f"{_fmt(T.PRED_HORIZON_WEEKS)} haftada {limit} dan oshishi mumkin")
    if len(parts) > 1:
        text += f" (diastolik ham: {_arrow(parts[1][1][0])})"
    red = any(p[3] for p in parts)
    if red:
        text += f" — hozir {T.PRED_BP_RED_SYS}/{T.PRED_BP_RED_DIA} dan yuqori"
    return _hit("P01", text, "red" if red else "yellow", **meta)


def _p02_hb(preg: dict, last: list[dict]) -> dict | None:
    ser = _series(preg, last, "hemoglobin_g_l")
    if ser is None or not _monotonic(ser[0], up=False):
        return None
    proj = projected(*ser)
    if proj >= T.PRED_HB_TARGET:
        return None
    vals = ser[0]
    return _hit("P02", f"Gemoglobin {len(vals)} ko'rikda ketma-ket pasaymoqda: {_arrow(vals)} g/L; shu sur'atda "
                       f"{_fmt(T.PRED_HORIZON_WEEKS)} haftada {T.PRED_HB_TARGET} dan pastga tushishi mumkin",
                **_meta(last, vals, ser[1], "down", "g/L", "hemoglobin_g_l", proj))


def _p03_weight(preg: dict, last: list[dict]) -> dict | None:
    ser = _series(preg, last, "weight_kg")
    if ser is None or ser[1][0] < T.TREND_WEIGHT_MIN_WEEKS:
        return None
    vals, weeks = ser
    rates = [(b - a) / (wb - wa) for a, b, wa, wb in zip(vals, vals[1:], weeks, weeks[1:], strict=False)]
    if not all(r > T.PRED_WEIGHT_GAIN_KG_PER_WEEK for r in rates):
        return None
    return _hit("P03", f"Vazn {len(vals)} ko'rikda haftasiga {_fmt(T.PRED_WEIGHT_GAIN_KG_PER_WEEK)} kg dan tez "
                       f"ortmoqda: {_arrow(vals)} kg ({', '.join(f'{r:.1f}' for r in rates)} kg/hafta) — "
                       "shish / preeklampsiya xavf belgisi",
                **_meta(last, vals, weeks, "up", "kg", "weight_kg"))


def _p04_fundal(preg: dict, last: list[dict]) -> dict | None:
    ser = _series(preg, last, "fundal_height_cm")
    if ser is None or ser[1][0] < T.TREND_FUNDAL_MIN_WEEKS:
        return None
    fundal, weeks = ser
    lag = [round(w - f, 1) for f, w in zip(fundal, weeks, strict=True)]
    if not _monotonic(lag, up=True) or lag[-1] < T.PRED_FUNDAL_MIN_LAG_CM:
        return None
    return _hit("P04", f"Bachadon tubi balandligi muddatdan tobora orqada qolmoqda: farq {_arrow(lag)} sm "
                       f"({len(lag)} ko'rik) — homila o'sishi sekinlashishi shubhasi",
                **_meta(last, lag, weeks, "up", "sm", "fundal_lag_cm"))


def _p05_ml(last: list[dict], probs: list[float | None], weeks: list[float]) -> dict | None:
    if len(probs) < T.PRED_MIN_VISITS or any(p is None for p in probs):
        return None
    if not _monotonic(probs, up=True) or probs[-1] - probs[0] < T.PRED_ML_RISE_TOTAL:
        return None
    return _hit("P05", f"Model bo'yicha xavf ehtimoli {len(probs)} ko'rikda ketma-ket oshmoqda: "
                       + " → ".join(f"{p:.0%}" for p in probs),
                **_meta(last, [round(p * 100, 1) for p in probs], weeks, "up", "%", "ml_probability"))


def predictive_hits(preg: dict, visits: list[dict], ml_probs: list[float | None] | None = None) -> list[dict]:
    """P01-P05 over the last PRED_MIN_VISITS visits. `ml_probs`: ML probability of each of those visits."""
    if len(visits) < T.PRED_MIN_VISITS:
        return []
    last = visits[-T.PRED_MIN_VISITS:]
    hits = [h for h in (_p01_bp(preg, last), _p02_hb(preg, last), _p03_weight(preg, last), _p04_fundal(preg, last))
            if h is not None]
    if ml_probs is not None:
        p5 = _p05_ml(last, list(ml_probs)[-T.PRED_MIN_VISITS:], [visit_weeks(preg, v) for v in last])
        if p5 is not None:
            hits.append(p5)
    return hits


def trend_hits(preg: dict, visits: list[dict], ml_prob: float | None = None,
               prev_ml_prob: float | None = None, prev_ml_probs: list[float | None] | None = None) -> list[dict]:
    """All trend hits for the LAST visit. `prev_ml_probs`: ML probabilities of the earlier visits (oldest first)."""
    if prev_ml_probs and prev_ml_prob is None:
        prev_ml_prob = prev_ml_probs[-1]
    ml_series = (list(prev_ml_probs) + [ml_prob]) if prev_ml_probs is not None and ml_prob is not None else None
    pred = predictive_hits(preg, visits, ml_series)
    superseded = {SUPERSEDES[h["code"]] for h in pred}
    return pred + [h for h in _pair_hits(preg, visits, ml_prob, prev_ml_prob) if h["code"] not in superseded]


def trend_zone(hits: list[dict], clinical_yellow: bool = False) -> str:
    """RED: any red trend hit, 2+ trend hits, or a predictive hit + a clinical (Tier A) yellow rule."""
    if not hits:
        return "green"
    if len(hits) >= 2 or any(h.get("zone") == "red" for h in hits):
        return "red"
    if clinical_yellow and any(is_predictive(h) for h in hits):
        return "red"
    return "yellow"
