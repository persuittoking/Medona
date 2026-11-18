"""Task 07 part A: predictive multi-visit trend rules P01-P05 (slope per week over the last 3 visits)."""
import pytest

from app.risk import thresholds as T
from app.risk.engine import score_pregnancy
from app.risk.trends import predictive_hits, projected, slope_per_week, trend_hits, trend_zone
from tests.test_risk_engine import FakeModel, preg, visit


def three(key: str, vals, weeks=(26, 28, 30), **cur_over) -> list[dict]:
    """Three visits (oldest first) with `key` set to `vals`, at the given gestational weeks."""
    out = []
    for i, (val, w) in enumerate(zip(vals, weeks, strict=True)):
        extra = cur_over if i == len(vals) - 1 else {}
        out.append(visit(w, days_before=int(round((weeks[-1] - w) * 7)), **{key: val}, **extra))
    return out


def codes(hits) -> set[str]:
    return {h["code"] for h in hits}


# ---------- P01 blood pressure ----------
def test_p01_rising_bp_projected_over_threshold_is_yellow():
    vs = three("systolic", [116, 120, 126])  # 2.5/week -> 131 in 2 weeks: no
    assert "P01" not in codes(predictive_hits(preg(30), vs))
    vs = three("systolic", [112, 120, 128])  # 4/week -> 136: no (needs 140)
    assert "P01" not in codes(predictive_hits(preg(30), vs))
    vs = three("diastolic", [72, 78, 84])  # 3/week -> 90 projected, 84 now (< 85) -> YELLOW
    hit = next(h for h in predictive_hits(preg(30), vs) if h["code"] == "P01")
    assert hit["zone"] == "yellow" and hit["kind"] == "trend" and hit["values"] == [72, 78, 84]
    assert hit["direction"] == "up" and hit["projected"] == 90 and len(hit["dates"]) == 3


def test_p01_red_when_already_high_normal():
    vs = three("systolic", [116, 125, 134])  # 4.5/week -> 143; 134 >= 130 now -> RED
    hit = next(h for h in trend_hits(preg(30), vs) if h["code"] == "P01")
    assert hit["zone"] == "red"
    res = score_pregnancy(preg(30), vs, model=False)
    assert res["zone"] == "red" and res["rule_zone"] == "green"  # red by trend only


def test_p01_text_contains_the_three_values_and_no_diagnosis():
    vs = three("systolic", [118, 126, 134])
    hit = next(h for h in predictive_hits(preg(30), vs) if h["code"] == "P01")
    assert "118 → 126 → 134" in hit["uz_text"] and "140" in hit["uz_text"] and "2 haftada" in hit["uz_text"]
    assert "tashxis" not in hit["uz_text"].lower() and "diagnoz" not in hit["uz_text"].lower()


def test_p01_uneven_spacing_uses_slope_per_week():
    # Same values, +8 per visit. Over 2+2 weeks -> 4/week -> 142 projected: P01.
    assert "P01" in codes(predictive_hits(preg(30), three("systolic", [118, 126, 134], weeks=(26, 28, 30))))
    # Over 8+2 weeks -> 1.6/week -> 137.2: no P01 although the per-visit steps are identical.
    assert "P01" not in codes(predictive_hits(preg(30), three("systolic", [118, 126, 134], weeks=(20, 28, 30))))
    vals, weeks = [118.0, 126.0, 134.0], [20.0, 28.0, 30.0]
    assert slope_per_week(vals, weeks) == pytest.approx(1.6) and projected(vals, weeks) == pytest.approx(137.2)


def test_p01_zigzag_values_do_not_fire():
    assert "P01" not in codes(predictive_hits(preg(30), three("systolic", [120, 118, 136])))
    assert "P01" not in codes(predictive_hits(preg(30), three("systolic", [118, 134, 134])))  # flat step


def test_p01_needs_20_weeks():
    vs = three("systolic", [116, 125, 134], weeks=(14, 16, 18))
    assert "P01" not in codes(predictive_hits(preg(18), vs))


def test_too_short_interval_is_skipped():
    vs = three("systolic", [116, 125, 134], weeks=(28, 29.8, 30))
    assert "P01" not in codes(predictive_hits(preg(30), vs))


# ---------- P02-P05 ----------
def test_p02_hb_falling_projected_below_100():
    hits = predictive_hits(preg(30), three("hemoglobin_g_l", [122, 113, 104], weeks=(22, 26, 30)))
    hit = next(h for h in hits if h["code"] == "P02")
    assert hit["zone"] == "yellow" and hit["direction"] == "down" and "122 → 113 → 104" in hit["uz_text"]
    assert "P02" not in codes(predictive_hits(preg(30), three("hemoglobin_g_l", [122, 116, 110])))  # -> 104
    assert "P02" not in codes(predictive_hits(preg(30), three("hemoglobin_g_l", [110, 104, 108])))  # zig-zag


def test_p03_weight_gain_above_limit_at_both_steps():
    assert "P03" in codes(predictive_hits(preg(30), three("weight_kg", [70, 72.4, 74.8])))   # 1.2/week twice
    assert "P03" not in codes(predictive_hits(preg(30), three("weight_kg", [70, 70.8, 74])))  # 0.4 then 1.6


def test_p04_fundal_lag_growing():
    vs = three("fundal_height_cm", [25.5, 26.5, 27.5])  # lag 0.5 -> 1.5 -> 2.5 cm at 26/28/30 w
    assert "P04" in codes(predictive_hits(preg(30), vs))
    assert "P04" not in codes(predictive_hits(preg(30), three("fundal_height_cm", [25.5, 27.5, 29.5])))


def test_p05_ml_rising_at_each_step():
    vs = [visit(26, days_before=28), visit(28, days_before=14), visit(30)]
    hits = trend_hits(preg(30), vs, ml_prob=0.30, prev_ml_probs=[0.10, 0.18])
    assert "P05" in codes(hits) and "T05" not in codes(hits)  # P05 supersedes T05
    assert "P05" not in codes(trend_hits(preg(30), vs, ml_prob=0.20, prev_ml_probs=[0.10, 0.18]))  # +0.10 only
    assert "P05" not in codes(trend_hits(preg(30), vs, ml_prob=0.30, prev_ml_probs=[0.20, 0.12]))  # not monotonic


# ---------- combination, fallback, safety ----------
def test_only_two_visits_uses_old_t_rules_only():
    vs = [visit(26, days_before=28, systolic=110), visit(30, systolic=134)]
    assert codes(trend_hits(preg(30), vs)) == {"T02"} and not predictive_hits(preg(30), vs)


def test_p_rule_supersedes_t_rule_for_same_signal():
    vs = three("systolic", [110, 112, 134])  # +22 last step (T02) and rising -> P01 replaces T02
    assert codes(trend_hits(preg(30), vs)) == {"P01"}


def test_two_p_hits_make_red():
    vs = three("diastolic", [72, 78, 84])
    for v, hb in zip(vs, (122, 113, 104), strict=True):  # -4.5 g/L per week -> projected 95
        v["hemoglobin_g_l"] = hb
    res = score_pregnancy(preg(30), vs, model=False)
    assert {"P01", "P02"} <= codes(res["trend_hits"]) and res["zone"] == "red"


def test_p_hit_plus_clinical_yellow_is_red():
    vs = three("diastolic", [72, 78, 84])
    assert score_pregnancy(preg(30), vs, model=False)["zone"] == "yellow"
    res = score_pregnancy(preg(30, previous_cs=True), vs, model=False)  # Y03 Tier A + P01
    assert res["zone"] == "red" and "QIZIL" in res["explanation_uz"]
    # a Tier B factor (via the Y16 combination) is not a clinical yellow rule -> stays yellow
    assert score_pregnancy(preg(30, rh_negative=True), vs, model=False)["zone"] == "yellow"
    assert trend_zone([{"code": "T01", "zone": "yellow"}], clinical_yellow=True) == "yellow"  # T-hits: as before


def test_rules_still_override_ml_with_trends():
    vs = three("diastolic", [72, 78, 84])
    assert score_pregnancy(preg(30), vs, model=FakeModel(0.0))["zone"] == "yellow"  # ML 0 cannot lower P01
    vs[-1]["systolic"] = 165
    assert score_pregnancy(preg(30), vs, model=FakeModel(0.0))["zone"] == "red"


def test_thresholds_live_in_config():
    assert T.PRED_MIN_VISITS == 3 and T.PRED_HORIZON_WEEKS == 2
    assert T.PRED_BP_RED_SYS == 130 and T.PRED_BP_RED_DIA == 85


def test_seeded_trend_patients_are_red_or_yellow_by_trend_only(client):
    from app.db import SessionLocal
    from app.models import Patient
    from app.services.scoring import latest_assessment

    with SessionLocal() as db:
        pats = db.query(Patient).filter(Patient.code.like("%-TRND%")).all()
        assert len(pats) == 9  # 3 per polyclinic
        for p in pats:
            ra = latest_assessment(db, p.pregnancies[0].id)
            assert ra.zone in ("yellow", "red"), p.code
            assert not [h for h in ra.rule_hits if h["zone"] in ("red", "yellow")], p.code  # no static rule
            assert any(h["code"].startswith("P") and len(h["values"]) == 3 for h in ra.trend_hits), p.code
        demo1 = db.query(Patient).filter_by(code="QQR-NUK-DEMO1").one()
        assert demo1.pregnancies[0].current_zone == "yellow"
