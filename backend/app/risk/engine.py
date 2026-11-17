"""Risk engine: final zone = max(rule zone, trend zone, ML zone).

Hard clinical rules always apply; the ML model can only RAISE the zone, never lower it.
"""
from app.risk import thresholds as T
from app.risk.features import build_features
from app.risk.ml import Model, load_model
from app.risk.rules import FACTOR, ZONE_ORDER, combine_factors, max_zone, red_rules, visit_notes, yellow_rules
from app.risk.trends import trend_hits, trend_zone

ZONE_UZ = {"red": "QIZIL", "yellow": "SARIQ", "green": "YASHIL"}


def rule_zone(hits: list[dict]) -> str:
    """Zone from rule hits; Tier B factors ("factor") never set a zone on their own."""
    return max_zone(*[h["zone"] for h in hits if h["zone"] in ZONE_ORDER])


def ml_zone(prob: float | None) -> str:
    if prob is None:
        return "green"
    if prob >= T.ML_RED:
        return "red"
    return "yellow" if prob >= T.ML_YELLOW else "green"


def explanation_uz(zone: str, rules: list[dict], trends: list[dict], prob: float | None,
                   zml: str, shap_top: list[dict]) -> str:
    parts = [f"Zona: {ZONE_UZ[zone]}."]
    active = [h for h in rules if h["zone"] != FACTOR]
    factors = [h for h in rules if h["zone"] == FACTOR]
    if active:
        parts.append("Klinik qoidalar: " + "; ".join(h["uz_text"] for h in active) + ".")
    if factors:
        parts.append("Xavf omillari (kuzatuv uchun): " + "; ".join(h["uz_text"] for h in factors) + ".")
    if trends:
        parts.append("Dinamika: " + "; ".join(h["uz_text"] for h in trends) + ".")
    if prob is not None:
        ups = [s["uz_label"] for s in shap_top if s["direction"] == "up"][:3]
        txt = f"Model bo'yicha xavf ehtimoli {prob:.0%}"
        if ups:
            txt += " (asosiy omillar: " + ", ".join(ups) + ")"
        if zml == zone != "green" and rule_zone(rules) != zone and trend_zone(trends) != zone:
            txt += " — zona model tomonidan oshirildi"
        parts.append(txt + ".")
    if zone == "green" and not active and not trends:
        parts.append("Xavf belgilari aniqlanmadi.")
    parts.append("Bu qaror qabul qilishda yordam; yakuniy qarorni shifokor qabul qiladi.")
    return " ".join(parts)


def score_pregnancy(preg: dict, visits: list[dict], prev_ml_prob: float | None = None,
                    model: Model | None | bool = True) -> dict:
    """Score the LAST visit in `visits` (chronological). `model=False` disables ML."""
    if not visits:
        raise ValueError("at least one visit is required")
    mdl = load_model() if model is True else (model or None)
    cur, prev = visits[-1], (visits[-2] if len(visits) > 1 else None)

    rules = red_rules(preg, cur) + yellow_rules(preg, cur, prev)
    prob, shap_top, version = None, [], None
    if mdl is not None:
        feats = build_features(preg, visits)
        prob = round(mdl.predict(feats), 4)
        shap_top = mdl.explain(feats)
        version = mdl.version
    trends = trend_hits(preg, visits, prob, prev_ml_prob)
    rules = combine_factors(rules, trends)
    zr, zt, zml = rule_zone(rules), trend_zone(trends), ml_zone(prob)
    zone = max_zone(zr, zt, zml)
    return {
        "zone": zone,
        "rule_zone": zr,
        "trend_zone": zt,
        "ml_zone": zml,
        "ml_probability": prob,
        "rule_hits": rules,
        "trend_hits": trends,
        "notes": visit_notes(preg, cur),
        "shap_top": shap_top,
        "model_version": version,
        "explanation_uz": explanation_uz(zone, rules, trends, prob, zml, shap_top),
    }
