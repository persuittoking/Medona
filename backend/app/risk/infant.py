"""Infant (0-12 months) risk engine: clinical rules + growth trends, NO ML model.

- Day 0-28: the neonatal rules N01-N13 (app/risk/newborn.py) plus the infant-only signs below that N01-N13 do not
  cover (vomiting, diarrhoea, blood in stool, lethargy) and the growth / vaccine / feeding / follow-up rules.
- Day 29-365: I01-I14 (WHO IMCI danger signs for the young infant and the child 2-12 months).
- Trends G01/G02 over the last checks (weight-for-age z-score falling, weight not increasing).

Zone = max(rule zone, trend zone). Trend zone: each hit >= YELLOW; any red hit, 2+ hits, or a trend hit together
with any yellow rule ("boshqa sariq belgi") -> RED. Texts say "xavf belgisi / shubha", never a diagnosis.
All thresholds: app/risk/thresholds.py (INF_*, WFA_TABLE, VACCINE_SCHEDULE).
"""
from __future__ import annotations

from datetime import date, timedelta

from app.risk import thresholds as T
from app.risk.engine import ZONE_UZ
from app.risk.features import as_date
from app.risk.newborn import newborn_hits
from app.risk.rules import max_zone
from app.risk.trends import _arrow, _monotonic

FEEDING = ("exclusive_breast", "mixed", "formula", "complementary")
FEEDING_UZ = {"exclusive_breast": "faqat ko'krak suti", "mixed": "aralash", "formula": "sun'iy aralashma",
              "complementary": "qo'shimcha ovqat"}
NO_ML_UZ = "Bolalar uchun faqat klinik qoidalar va trendlar ishlatiladi (ML modeli qo'llanilmaydi)."
GROWTH_CODES = ("G01", "G02")


def _hit(code: str, zone: str, text: str) -> dict:
    return {"code": code, "zone": zone, "uz_text": text}


# ---------------- age, growth reference, vaccines ----------------
def age_days(birth: date, on: date) -> int:
    return (as_date(on) - as_date(birth)).days


def age_months(birth: date, on: date) -> float:
    return round(age_days(birth, on) / T.DAYS_PER_MONTH, 1)


def age_text(days: int) -> str:
    """'12 kun' under 2 months, otherwise '4 oy'."""
    return f"{days} kun" if days < T.YOUNG_INFANT_DAYS else f"{int(days // T.DAYS_PER_MONTH)} oy"


def wfa_ref(sex: str, months: float) -> tuple[float, float]:
    """(median kg, SD kg) for the sex at this age, linear between the WHO monthly values."""
    table = T.WFA_TABLE["f" if sex == "f" else "m"]
    m = min(max(months, 0.0), len(table) - 1.0)
    i = min(int(m), len(table) - 2)
    frac = m - i
    (med0, low0), (med1, low1) = table[i], table[i + 1]
    med = med0 + (med1 - med0) * frac
    low = low0 + (low1 - low0) * frac
    return med, (med - low) / 2


def wfa_z(sex: str, days: int, weight_kg: float) -> float:
    med, sd = wfa_ref(sex, days / T.DAYS_PER_MONTH)
    return round((weight_kg - med) / sd, 2)


def vaccine_status(birth: date, given: set[str] | list[str], on: date) -> list[dict]:
    """Every first-year dose: due date and status given | overdue (> INF_VACCINE_OVERDUE_DAYS late) | due | upcoming."""
    given = set(given)
    out = []
    for code, family, due_day in T.VACCINE_SCHEDULE:
        due = as_date(birth) + timedelta(days=due_day)
        late = (as_date(on) - due).days
        if code in given:
            status = "given"
        elif late > T.INF_VACCINE_OVERDUE_DAYS:
            status = "overdue"
        elif late >= 0:
            status = "due"
        else:
            status = "upcoming"
        out.append({"code": code, "family": family, "due_date": due, "status": status, "days_late": max(0, late)})
    return out


def overdue_vaccines(birth: date, given: set[str] | list[str], on: date) -> list[str]:
    return [v["code"] for v in vaccine_status(birth, given, on) if v["status"] == "overdue"]


def given_vaccines(checks: list[dict]) -> set[str]:
    return {c for ck in checks for c in (ck.get("vaccines_given") or [])}


# ---------------- rules ----------------
def _danger_signs(c: dict, days: int) -> list[dict]:
    """I01-I09 (day 29+), or only the signs N01-N13 do not cover (day 0-28)."""
    neonate = days <= T.NEONATAL_DAYS
    hits: list[dict] = []
    if not neonate and c.get("not_feeding_well"):
        hits.append(_hit("I01", "red", "Emish / ovqatlana olmaydi"))
    if c.get("vomiting_everything"):
        hits.append(_hit("I02", "red", "Hamma narsani qayt qiladi"))
    if not neonate and c.get("convulsions"):
        hits.append(_hit("I03", "red", "Talvasa"))
    if c.get("lethargic") or (not neonate and c.get("movement_only_when_stimulated")):
        hits.append(_hit("I04", "red", "Holsiz / hushi xira"))
    rr = c.get("resp_rate")
    limit = T.INF_RESP_FAST_UNDER_2M if days < T.YOUNG_INFANT_DAYS else T.INF_RESP_FAST_2_12M
    if not neonate and rr is not None and rr >= limit:
        hits.append(_hit("I05", "red", f"Yoshiga nisbatan tez nafas ({rr}/daq, me'yor < {limit})"))
    if not neonate and c.get("severe_chest_indrawing"):
        hits.append(_hit("I06", "red", "Ko'krak qafasining kuchli tortilishi"))
    t = c.get("temperature_c")
    if not neonate and t is not None and ((days < T.YOUNG_INFANT_DAYS and t >= T.INF_TEMP_HIGH_UNDER_2M)
                                          or t < T.INF_TEMP_LOW):
        hits.append(_hit("I07", "red", f"Harorat xavfli ({t:g}°C)"))
    if c.get("blood_in_stool"):
        hits.append(_hit("I08", "red", "Najasda qon"))
    dd = c.get("diarrhoea_days")
    if dd is not None and dd >= T.INF_DIARRHOEA_PERSISTENT_DAYS:
        hits.append(_hit("I09", "red", f"Uzoq davom etayotgan diareya ({dd} kun)"))
    return hits


def _yellow_signs(child: dict, c: dict | None, checks: list[dict], days: int, today: date) -> list[dict]:
    hits: list[dict] = []
    c = c or {}
    w = c.get("weight_g")
    if w and child.get("sex"):
        z = wfa_z(child["sex"], days, w / 1000)
        if z < T.INF_WFA_LOW_Z:
            hits.append(_hit("I10", "yellow", f"Yoshiga nisbatan vazn kam ({w / 1000:g} kg, z = {z:+.1f})"))
    od = overdue_vaccines(child["birth_date"], given_vaccines(checks), today)
    if od:
        hits.append(_hit("I11", "yellow", f"Emlash {T.INF_VACCINE_OVERDUE_DAYS} kundan ortiq kechikkan: " + ", ".join(od)))
    cd = c.get("cough_days")
    if cd is not None and cd >= T.INF_COUGH_CHRONIC_DAYS:
        hits.append(_hit("I12", "yellow", f"Uzoq davom etayotgan yo'tal ({cd} kun)"))
    last = max((as_date(k["check_date"]) for k in checks), default=None)
    since = (today - (last or as_date(child["birth_date"]))).days
    if days > T.NEONATAL_DAYS and since > T.INF_CHECK_INTERVAL_DAYS:
        hits.append(_hit("I13", "yellow", f"Rejali ko'rik o'tkazilmagan ({since} kun)"))
    fd = c.get("feeding")
    if fd and fd != "exclusive_breast" and days < T.INF_EXCLUSIVE_BF_DAYS:
        hits.append(_hit("I14", "yellow", f"6 oygacha faqat ko'krak suti bilan emas ({FEEDING_UZ.get(fd, fd)})"))
    return hits


def infant_rule_hits(child: dict, checks: list[dict], today: date | None = None,
                     mother_red_3rd_trimester: bool = False) -> list[dict]:
    """Rule hits for the LAST check in `checks` (chronological; may be empty). `today`: date of the assessment."""
    cur = checks[-1] if checks else None
    today = as_date(today or (cur["check_date"] if cur else date.today()))
    on = as_date(cur["check_date"]) if cur else today
    days = age_days(child["birth_date"], on)
    hits: list[dict] = []
    if days <= T.NEONATAL_DAYS:
        hits += newborn_hits(child, cur, mother_red_3rd_trimester=mother_red_3rd_trimester, today=today)
    hits += _danger_signs(cur or {}, days)
    hits += _yellow_signs(child, cur, checks, days, today)
    return hits


# ---------------- growth trends ----------------
def _weighed(checks: list[dict]) -> list[dict]:
    return [c for c in checks if c.get("weight_g")]


def _gaps_ok(rows: list[dict]) -> bool:
    ds = [as_date(r["check_date"]) for r in rows]
    return all((b - a).days >= T.INF_MIN_TREND_GAP_DAYS for a, b in zip(ds, ds[1:], strict=False))


def _meta(child: dict, rows: list[dict], vals: list[float], direction: str, unit: str, param: str) -> dict:
    return {"kind": "trend", "param": param, "values": [round(v, 2) for v in vals], "direction": direction,
            "unit": unit, "dates": [as_date(r["check_date"]).isoformat() for r in rows],
            "ages_months": [age_months(child["birth_date"], r["check_date"]) for r in rows]}


def growth_trend_hits(child: dict, checks: list[dict]) -> list[dict]:
    """G01: WFA z fell >= INF_Z_DROP since the previous check. G02: weight not increasing at 2 consecutive checks."""
    rows = _weighed(checks)
    if not rows or rows[-1] is not (checks[-1] if checks else None) or not child.get("sex"):
        return []  # trends only when the current check has a weight
    hits: list[dict] = []
    if len(rows) >= 2 and _gaps_ok(rows[-2:]):
        pair = rows[-2:]
        zs = [wfa_z(child["sex"], age_days(child["birth_date"], r["check_date"]), r["weight_g"] / 1000) for r in pair]
        if zs[0] - zs[1] >= T.INF_Z_DROP:
            hits.append({"code": "G01", "zone": "yellow",
                         "uz_text": f"Vazn-yosh z-ko'rsatkichi pasaygan ({zs[0]:+.1f} → {zs[1]:+.1f}) — o'sish sekinlashishi shubhasi",
                         **_meta(child, pair, zs, "down", "z", "wfa_z")})
    n = T.INF_PLATEAU_STEPS + 1
    if len(rows) >= n and _gaps_ok(rows[-n:]):
        last = rows[-n:]
        kg = [r["weight_g"] / 1000 for r in last]
        if not any(b > a for a, b in zip(kg, kg[1:], strict=False)):
            trend = "kamaymoqda" if _monotonic(kg, up=False) else "ortmayapti"
            hits.append({"code": "G02", "zone": "yellow",
                         "uz_text": f"O'sish to'xtashi: vazn {len(kg)} ko'rikda {trend} ({_arrow(kg)} kg)",
                         **_meta(child, last, kg, "down", "kg", "weight_kg")})
    return hits


def infant_trend_zone(trends: list[dict], rule_yellow: bool) -> str:
    if not trends:
        return "green"
    if len(trends) >= 2 or rule_yellow or any(h["zone"] == "red" for h in trends):
        return "red"
    return "yellow"


# ---------------- combined ----------------
def explanation_uz(zone: str, rules: list[dict], trends: list[dict]) -> str:
    parts = [f"Zona: {ZONE_UZ[zone]}."]
    if rules:
        parts.append("Klinik qoidalar: " + "; ".join(h["uz_text"] for h in rules) + ".")
    if trends:
        parts.append("Dinamika: " + "; ".join(h["uz_text"] for h in trends) + ".")
        if infant_trend_zone(trends, False) != "red" and any(h["zone"] == "yellow" for h in rules):
            parts.append("O'sish trendi boshqa sariq belgi bilan birga — zona QIZILga oshirildi.")
    if not rules and not trends:
        parts.append("Xavf belgilari aniqlanmadi.")
    parts.append(NO_ML_UZ)
    parts.append("Bu qaror qabul qilishda yordam; yakuniy qarorni shifokor qabul qiladi.")
    return " ".join(parts)


def score_infant(child: dict, checks: list[dict], today: date | None = None,
                 mother_red_3rd_trimester: bool = False) -> dict:
    """Score the LAST check (or the child without checks). Same result shape as score_pregnancy, ML fields empty."""
    rules = infant_rule_hits(child, checks, today, mother_red_3rd_trimester)
    trends = growth_trend_hits(child, checks)
    zr = max_zone(*[h["zone"] for h in rules]) if rules else "green"
    zt = infant_trend_zone(trends, any(h["zone"] == "yellow" for h in rules))
    zone = max_zone(zr, zt)
    return {"zone": zone, "rule_zone": zr, "trend_zone": zt, "ml_zone": "green", "ml_probability": None,
            "rule_hits": rules, "trend_hits": trends, "notes": [NO_ML_UZ], "shap_top": [], "model_version": None,
            "explanation_uz": explanation_uz(zone, rules, trends)}


def severity_score(result: dict) -> float:
    """0..1 ordering key for lists (NOT a probability): red 0.9+, yellow 0.5+, a little more per extra hit."""
    n = len(result["rule_hits"]) + len(result["trend_hits"])
    base = {"red": 0.9, "yellow": 0.5, "green": 0.0}[result["zone"]]
    return round(min(0.99, base + 0.02 * n), 2)

