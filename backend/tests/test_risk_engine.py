"""Risk engine tests: every rule just above / just below its threshold."""
import time
from datetime import date, timedelta

import pytest

from app.risk import thresholds as T
from app.risk.engine import ml_zone, score_pregnancy
from app.risk.newborn import newborn_hits, newborn_zone
from app.risk.rules import red_rules, yellow_rules
from app.risk.trends import trend_hits, trend_zone

TODAY = date(2026, 6, 1)


def preg(weeks: float = 30, age: float = 26, **over) -> dict:
    lmp = TODAY - timedelta(days=int(weeks * 7))
    p = {"lmp_date": lmp, "booking_date": lmp + timedelta(days=70), "birth_date": TODAY - timedelta(days=int(age * 365.25)),
         "gravidity": 2, "parity": 1, "previous_cs": False, "hist_stillbirth": False, "hist_preterm": False,
         "miscarriages_count": 0, "hist_preeclampsia": False, "hist_pph": False, "diabetes": False,
         "chronic_htn": False, "heart": False, "kidney": False, "thyroid": False, "epilepsy": False,
         "multiple_pregnancy": False, "rh_negative": False, "interpregnancy_months": 36, "height_cm": 160.0,
         "booking_weight_kg": 60.0, "distance_to_perinatal_km": 10.0}
    p.update(over)
    return p


def visit(weeks: float = 30, days_before: int = 0, **over) -> dict:
    v = {"visit_date": TODAY - timedelta(days=days_before), "gestational_weeks": weeks, "systolic": 115,
         "diastolic": 72, "proteinuria": "neg", "hemoglobin_g_l": 120, "fasting_glucose_mmol": 4.5,
         "weight_kg": 70.0, "temperature_c": 36.6, "fetal_heart_rate": 140, "fundal_height_cm": weeks,
         "symptoms": []}
    v.update(over)
    return v


def red_codes(p, v):
    return {h["code"] for h in red_rules(p, v)}


def yellow_codes(p, v, prev=None):
    return {h["code"] for h in yellow_rules(p, v, prev)}


# ---------- baseline ----------
def test_healthy_visit_has_no_hits():
    p = preg()
    assert red_codes(p, visit()) == set()
    assert yellow_codes(p, visit()) == set()
    assert score_pregnancy(p, [visit()], model=False)["zone"] == "green"


# ---------- RED rules ----------
@pytest.mark.parametrize("s,d,hit", [(160, 80, True), (159, 80, False), (120, 110, True), (120, 109, False)])
def test_r01_severe_hypertension(s, d, hit):
    assert ("R01" in red_codes(preg(), visit(systolic=s, diastolic=d))) is hit


@pytest.mark.parametrize("s,d,prot,hit", [(140, 80, "+1", True), (139, 89, "+1", False),
                                          (130, 90, "+2", True), (145, 92, "trace", False)])
def test_r02_preeclampsia(s, d, prot, hit):
    assert ("R02" in red_codes(preg(), visit(systolic=s, diastolic=d, proteinuria=prot))) is hit


@pytest.mark.parametrize("hb,hit", [(69, True), (70, False)])
def test_r03_severe_anaemia(hb, hit):
    assert ("R03" in red_codes(preg(), visit(hemoglobin_g_l=hb))) is hit


@pytest.mark.parametrize("w,hit", [(20, True), (19.9, False)])
def test_r04_bleeding_after_20_weeks(w, hit):
    assert ("R04" in red_codes(preg(w), visit(w, symptoms=["bleeding"]))) is hit


@pytest.mark.parametrize("syms,bp,hit", [
    (["seizures"], (115, 72), True),
    (["severe_headache", "visual_disturbance"], (115, 72), True),
    (["severe_headache"], (115, 72), False),
    (["epigastric_pain"], (140, 85), True),
    (["epigastric_pain"], (139, 89), False),
    (["dyspnea"], (115, 72), True),
])
def test_r05_danger_symptoms(syms, bp, hit):
    assert ("R05" in red_codes(preg(), visit(symptoms=syms, systolic=bp[0], diastolic=bp[1]))) is hit


@pytest.mark.parametrize("fhr,w,hit", [(109, 30, True), (110, 30, False), (161, 30, True), (160, 30, False), (100, 19, False)])
def test_r06_fetal_heart_rate(fhr, w, hit):
    assert ("R06" in red_codes(preg(w), visit(w, fetal_heart_rate=fhr))) is hit


@pytest.mark.parametrize("w,hit", [(28, True), (27.9, False)])
def test_r07_reduced_fetal_movement(w, hit):
    assert ("R07" in red_codes(preg(w), visit(w, symptoms=["reduced_fetal_movement"]))) is hit


@pytest.mark.parametrize("t,hit", [(38.0, True), (37.9, False)])
def test_r08_fever(t, hit):
    assert ("R08" in red_codes(preg(), visit(temperature_c=t))) is hit


@pytest.mark.parametrize("w,sym,hit", [(36.9, "contractions", True), (37, "contractions", False), (30, "membrane_rupture", True)])
def test_r09_preterm_labour(w, sym, hit):
    assert ("R09" in red_codes(preg(w), visit(w, symptoms=[sym]))) is hit


@pytest.mark.parametrize("g,hit", [(7.0, True), (6.9, False)])
def test_r10_overt_hyperglycaemia(g, hit):
    assert ("R10" in red_codes(preg(), visit(fasting_glucose_mmol=g))) is hit


# ---------- YELLOW rules ----------
@pytest.mark.parametrize("age,hit", [(17.9, True), (18.1, False), (35.1, True), (34.9, False)])
def test_y01_age(age, hit):
    assert ("Y01" in yellow_codes(preg(age=age), visit())) is hit


@pytest.mark.parametrize("parity,hit", [(5, True), (4, False)])
def test_y02_grand_multipara(parity, hit):
    assert ("Y02" in yellow_codes(preg(parity=parity, gravidity=parity + 1), visit())) is hit


def test_y03_previous_cs():
    assert "Y03" in yellow_codes(preg(previous_cs=True), visit())


@pytest.mark.parametrize("over,hit", [({"hist_stillbirth": True}, True), ({"hist_preterm": True}, True),
                                      ({"miscarriages_count": 2}, True), ({"miscarriages_count": 1}, False),
                                      ({"hist_preeclampsia": True}, True), ({"hist_pph": True}, True)])
def test_y04_obstetric_history(over, hit):
    assert ("Y04" in yellow_codes(preg(**over), visit())) is hit


@pytest.mark.parametrize("s,d,prot,hit", [(140, 80, "neg", True), (159, 109, "trace", True), (139, 89, "neg", False),
                                          (160, 80, "neg", False), (145, 92, "+1", False)])
def test_y05_hypertension_without_proteinuria(s, d, prot, hit):
    assert ("Y05" in yellow_codes(preg(), visit(systolic=s, diastolic=d, proteinuria=prot))) is hit


@pytest.mark.parametrize("hb,hit", [(70, True), (99, True), (100, False), (69, False)])
def test_y06_moderate_anaemia(hb, hit):
    assert ("Y06" in yellow_codes(preg(), visit(hemoglobin_g_l=hb))) is hit


def test_mild_anaemia_is_a_note_not_a_zone():
    res = score_pregnancy(preg(), [visit(hemoglobin_g_l=105)], model=False)
    assert res["zone"] == "green" and any("Yengil anemiya" in n for n in res["notes"])


@pytest.mark.parametrize("g,hit", [(5.1, True), (6.9, True), (5.0, False), (7.0, False)])
def test_y07_gdm(g, hit):
    assert ("Y07" in yellow_codes(preg(), visit(fasting_glucose_mmol=g))) is hit


@pytest.mark.parametrize("w,hit", [(47.0, True), (48.0, False), (77.0, True), (76.5, False)])
def test_y08_bmi(w, hit):  # height 160 cm: BMI 18.4 / 18.75 / 30.1 / 29.9
    assert ("Y08" in yellow_codes(preg(booking_weight_kg=w), visit())) is hit


def test_y09_multiple():
    assert "Y09" in yellow_codes(preg(multiple_pregnancy=True), visit())


@pytest.mark.parametrize("flag", ["diabetes", "chronic_htn", "heart", "kidney", "thyroid", "epilepsy"])
def test_y10_chronic(flag):
    assert "Y10" in yellow_codes(preg(**{flag: True}), visit())


@pytest.mark.parametrize("m,hit", [(23, True), (24, False), (None, False)])
def test_y11_interpregnancy(m, hit):
    assert ("Y11" in yellow_codes(preg(interpregnancy_months=m), visit())) is hit


def test_y12_rh_negative():
    assert "Y12" in yellow_codes(preg(rh_negative=True), visit())


def test_y13_late_booking_and_overdue():
    p = preg(30)
    late = dict(p, booking_date=p["lmp_date"] + timedelta(days=13 * 7))
    assert "Y13" in yellow_codes(late, visit(30))
    assert "Y13" not in yellow_codes(dict(p, booking_date=p["lmp_date"] + timedelta(days=12 * 7)), visit(30))
    assert "Y13" in yellow_codes(p, visit(30), prev=visit(25, days_before=31))      # 3rd trimester: >30 days
    assert "Y13" not in yellow_codes(p, visit(30), prev=visit(26, days_before=30))
    p20 = preg(20)
    assert "Y13" in yellow_codes(p20, visit(20), prev=visit(13, days_before=46))    # otherwise: >45 days
    assert "Y13" not in yellow_codes(p20, visit(20), prev=visit(14, days_before=45))


@pytest.mark.parametrize("w,hit", [(41, True), (40.9, False)])
def test_y14_post_term(w, hit):
    assert ("Y14" in yellow_codes(preg(w), visit(w))) is hit


def test_y15_distance():
    assert "Y15" in yellow_codes(preg(distance_to_perinatal_km=80), visit())
    assert "Y15" not in yellow_codes(preg(distance_to_perinatal_km=50), visit())


# ---------- Tier A / Tier B ----------
TIER_A_CASES = {
    "Y02": dict(parity=5, gravidity=6), "Y03": dict(previous_cs=True), "Y04": dict(hist_stillbirth=True),
    "Y09": dict(multiple_pregnancy=True), "Y10": dict(diabetes=True),
}
TIER_B_CASES = {
    "Y01": dict(age=36), "Y08": dict(booking_weight_kg=80.0), "Y11": dict(interpregnancy_months=12),
    "Y12": dict(rh_negative=True), "Y13": dict(booking_date=None), "Y15": dict(distance_to_perinatal_km=80),
}


def _p(over: dict) -> dict:
    over = dict(over)
    p = preg(age=over.pop("age", 26), **{k: v for k, v in over.items() if k != "booking_date"})
    if "booking_date" in over:  # late booking: 14 weeks
        p["booking_date"] = p["lmp_date"] + timedelta(days=14 * 7)
    return p


def test_tier_config_matches_spec():
    assert set(T.TIER_B_RULES) == {"Y01", "Y08", "Y11", "Y12", "Y13", "Y15"}


@pytest.mark.parametrize("code", sorted(TIER_A_CASES))
def test_tier_a_alone_is_yellow(code):
    res = score_pregnancy(_p(TIER_A_CASES[code]), [visit()], model=False)
    assert code in {h["code"] for h in res["rule_hits"] if h["zone"] == "yellow"} and res["zone"] == "yellow"


@pytest.mark.parametrize("v_over,code", [({"systolic": 142}, "Y05"), ({"hemoglobin_g_l": 95}, "Y06"),
                                         ({"fasting_glucose_mmol": 5.5}, "Y07")])
def test_tier_a_visit_rules_alone_are_yellow(v_over, code):
    res = score_pregnancy(preg(), [visit(**v_over)], model=False)
    assert code in {h["code"] for h in res["rule_hits"]} and res["zone"] == "yellow"


def test_tier_a_y14_alone_is_yellow():
    assert score_pregnancy(preg(41.5), [visit(41.5)], model=False)["zone"] == "yellow"


@pytest.mark.parametrize("code", sorted(TIER_B_CASES))
def test_tier_b_alone_stays_green(code):
    res = score_pregnancy(_p(TIER_B_CASES[code]), [visit()], model=False)
    hits = {h["code"]: h["zone"] for h in res["rule_hits"]}
    assert hits == {code: "factor"}, hits
    assert res["zone"] == "green"
    assert "Xavf omillari (kuzatuv uchun)" in res["explanation_uz"]


def test_two_tier_b_factors_make_yellow():
    res = score_pregnancy(preg(age=36, rh_negative=True), [visit()], model=False)
    assert res["zone"] == "yellow" and "Y16" in {h["code"] for h in res["rule_hits"]}


def test_one_tier_b_plus_trend_makes_yellow():
    res = score_pregnancy(preg(rh_negative=True), [visit(26, days_before=28), visit(hemoglobin_g_l=104)], model=False)
    codes = {h["code"] for h in res["rule_hits"]}
    assert {"Y12", "Y16"} <= codes and res["trend_zone"] == "yellow" and res["rule_zone"] == "yellow"


def test_one_tier_b_without_trend_no_combo():
    res = score_pregnancy(preg(rh_negative=True), [visit(26, days_before=28), visit()], model=False)
    assert "Y16" not in {h["code"] for h in res["rule_hits"]} and res["zone"] == "green"


# ---------- trend rules ----------
def _trends(prev_over, cur_over, w=30, prev_w=26):
    p = preg(w)
    return {h["code"] for h in trend_hits(p, [visit(prev_w, days_before=28, **prev_over), visit(w, **cur_over)])}


def test_t01_hb_drop():
    assert "T01" in _trends({"hemoglobin_g_l": 120}, {"hemoglobin_g_l": 105})
    assert "T01" not in _trends({"hemoglobin_g_l": 120}, {"hemoglobin_g_l": 106})


def test_t02_bp_rise():
    assert "T02" in _trends({"systolic": 110}, {"systolic": 130})
    assert "T02" not in _trends({"systolic": 110}, {"systolic": 129})
    assert "T02" in _trends({"diastolic": 70}, {"diastolic": 85})
    assert "T02" not in _trends({"diastolic": 70}, {"diastolic": 84})


def test_t03_rapid_weight_gain():
    assert "T03" in _trends({"weight_kg": 70}, {"weight_kg": 74.2})   # 4.2 kg / 4 weeks
    assert "T03" not in _trends({"weight_kg": 70}, {"weight_kg": 74.0})
    assert "T03" not in _trends({"weight_kg": 70}, {"weight_kg": 75}, w=19, prev_w=15)  # before 20 weeks


def test_t04_fundal_lag():
    assert "T04" in _trends({}, {"fundal_height_cm": 27})
    assert "T04" not in _trends({}, {"fundal_height_cm": 27.1})
    assert "T04" not in _trends({}, {"fundal_height_cm": 20}, w=23.9, prev_w=20)


def test_t05_ml_rise():
    p, vs = preg(), [visit(26, days_before=28), visit()]
    assert "T05" in {h["code"] for h in trend_hits(p, vs, ml_prob=0.40, prev_ml_prob=0.25)}
    assert "T05" not in {h["code"] for h in trend_hits(p, vs, ml_prob=0.39, prev_ml_prob=0.25)}


def test_trend_zone_two_hits_red():
    assert trend_zone([]) == "green"
    assert trend_zone([{"code": "T01"}]) == "yellow"
    assert trend_zone([{"code": "T01"}, {"code": "T02"}]) == "red"


def test_two_trends_make_red_overall():
    p = preg()
    res = score_pregnancy(p, [visit(26, days_before=28), visit(hemoglobin_g_l=100, systolic=136)], model=False)
    assert {h["code"] for h in res["trend_hits"]} == {"T01", "T02"} and res["zone"] == "red"


# ---------- ML can only raise ----------
class FakeModel:
    version = "fake"

    def __init__(self, p):
        self.p = p

    def predict(self, feats):
        return self.p

    def explain(self, feats, k=5):
        return [{"feature": "systolic", "value": feats["systolic"], "shap": -1.0, "direction": "down",
                 "uz_label": "Sistolik bosim"}]


def test_ml_cannot_lower_a_red_rule():
    res = score_pregnancy(preg(), [visit(systolic=165)], model=FakeModel(0.0))
    assert res["zone"] == "red" and res["ml_zone"] == "green"


def test_ml_cannot_lower_a_yellow_rule():
    assert score_pregnancy(preg(previous_cs=True), [visit()], model=FakeModel(0.0))["zone"] == "yellow"
    assert score_pregnancy(preg(age=36, rh_negative=True), [visit()], model=FakeModel(0.0))["zone"] == "yellow"


def test_ml_can_raise():
    assert score_pregnancy(preg(), [visit()], model=FakeModel(T.ML_YELLOW))["zone"] == "yellow"
    assert score_pregnancy(preg(), [visit()], model=FakeModel(T.ML_RED))["zone"] == "red"
    assert ml_zone(None) == "green"


def test_explanation_has_disclaimer():
    assert "shifokor" in score_pregnancy(preg(), [visit(systolic=165)], model=False)["explanation_uz"]


# ---------- newborn ----------
NB = {"birth_weight_g": 3200, "gestational_weeks_at_birth": 39, "apgar_5": 9, "birth_date": TODAY - timedelta(days=2)}


@pytest.mark.parametrize("check,code", [
    ({"not_feeding_well": True}, "N01"), ({"convulsions": True}, "N02"), ({"resp_rate": 60}, "N03"),
    ({"severe_chest_indrawing": True}, "N04"), ({"temperature_c": 37.5}, "N05"), ({"temperature_c": 35.4}, "N05"),
    ({"movement_only_when_stimulated": True}, "N06"), ({"jaundice_first_24h": True}, "N07"),
    ({"jaundice_palms_soles": True}, "N07"),
])
def test_newborn_red_signs(check, code):
    hits = newborn_hits(NB, check)
    assert code in {h["code"] for h in hits} and newborn_zone(hits) == "red"


def test_newborn_below_thresholds_green():
    hits = newborn_hits(NB, {"resp_rate": 59, "temperature_c": 37.4})
    assert hits == [] and newborn_zone(hits) == "green"
    assert newborn_hits(NB, {"temperature_c": 35.5}) == []


@pytest.mark.parametrize("bw,code,zone", [(1499, "N08", "red"), (1500, "N09", "yellow"), (2499, "N09", "yellow")])
def test_newborn_weight(bw, code, zone):
    hits = newborn_hits(dict(NB, birth_weight_g=bw), {})
    assert code in {h["code"] for h in hits} and newborn_zone(hits) == zone
    assert newborn_hits(dict(NB, birth_weight_g=2500), {}) == []


def test_newborn_yellow_factors():
    assert "N10" in {h["code"] for h in newborn_hits(dict(NB, gestational_weeks_at_birth=36.9), {})}
    assert "N11" in {h["code"] for h in newborn_hits(dict(NB, apgar_5=6), {})}
    assert "N12" in {h["code"] for h in newborn_hits(NB, {}, mother_red_3rd_trimester=True)}
    assert "N13" in {h["code"] for h in newborn_hits(dict(NB, birth_date=TODAY - timedelta(days=4)), None, today=TODAY)}
    assert "N13" not in {h["code"] for h in newborn_hits(dict(NB, birth_date=TODAY - timedelta(days=3)), None, today=TODAY)}


# ---------- performance ----------
def test_scoring_under_100ms_with_real_model():
    from app.risk.ml import load_model

    mdl = load_model()
    if mdl is None:
        pytest.skip("model artifact not trained yet")
    p, vs = preg(), [visit(22, days_before=56), visit(26, days_before=28), visit()]
    score_pregnancy(p, vs, model=mdl)  # warm-up
    t0 = time.perf_counter()
    for _ in range(10):
        score_pregnancy(p, vs, model=mdl)
    assert (time.perf_counter() - t0) / 10 < 0.1
