"""Infant (0-12 months) risk engine: rules I01-I14, neonatal N-rules, WHO weight-for-age, vaccines, growth trends."""
from datetime import date, timedelta

import pytest

from app.risk import thresholds as T
from app.risk.infant import (
    NO_ML_UZ,
    age_text,
    growth_trend_hits,
    infant_trend_zone,
    overdue_vaccines,
    score_infant,
    vaccine_status,
    wfa_ref,
    wfa_z,
)

TODAY = date(2026, 6, 1)
ALL_DOSES = [c for c, _, _ in T.VACCINE_SCHEDULE]


def child(days: int, sex: str = "m", **kw) -> dict:
    return {"birth_date": TODAY - timedelta(days=days), "sex": sex, "birth_weight_g": 3300,
            "gestational_weeks_at_birth": 39.0, "apgar_5": 9, **kw}


def check(days_ago: int = 0, **kw) -> dict:
    """A normal check (all doses recorded as given, exclusive breastfeeding) with overrides."""
    base = {"check_date": TODAY - timedelta(days=days_ago), "vaccines_given": ALL_DOSES, "feeding": "exclusive_breast"}
    return {**base, **kw}


def codes(res: dict) -> set[str]:
    return {h["code"] for h in res["rule_hits"] + res["trend_hits"]}


def score(c: dict, checks: list[dict]) -> dict:
    return score_infant(c, checks, today=TODAY)


# ---------------- RED danger signs (2-12 months) ----------------
@pytest.mark.parametrize("sign,code", [
    ({"not_feeding_well": True}, "I01"), ({"vomiting_everything": True}, "I02"), ({"convulsions": True}, "I03"),
    ({"lethargic": True}, "I04"), ({"movement_only_when_stimulated": True}, "I04"), ({"resp_rate": 50}, "I05"),
    ({"severe_chest_indrawing": True}, "I06"), ({"temperature_c": 35.4}, "I07"), ({"blood_in_stool": True}, "I08"),
    ({"diarrhoea_days": 14}, "I09"),
])
def test_infant_red_signs(sign, code):
    res = score(child(120), [check(**sign)])
    assert code in codes(res) and res["zone"] == "red"


def test_healthy_infant_is_green_and_says_no_ml():
    res = score(child(120), [check(weight_g=6700, resp_rate=38, temperature_c=36.7, diarrhoea_days=13, cough_days=13)])
    assert res["zone"] == "green" and codes(res) == set()
    assert res["ml_probability"] is None and res["shap_top"] == [] and NO_ML_UZ in res["explanation_uz"]
    assert "yakuniy qarorni shifokor qabul qiladi" in res["explanation_uz"]


# ---------------- age-dependent thresholds ----------------
@pytest.mark.parametrize("age,rr,fast", [
    (45, 59, False), (45, 60, True),    # under 2 months: >= 60/min
    (59, 56, False),                    # still under 2 months: 56 is NOT fast
    (60, 50, True), (70, 49, False), (70, 56, True), (300, 50, True),  # 2-12 months: >= 50/min
])
def test_fast_breathing_threshold_depends_on_age(age, rr, fast):
    assert ("I05" in codes(score(child(age), [check(resp_rate=rr)]))) is fast


def test_fever_is_a_danger_sign_only_under_2_months():
    assert "I07" in codes(score(child(45), [check(temperature_c=38.0)]))
    assert "I07" not in codes(score(child(45), [check(temperature_c=37.9)]))
    assert "I07" not in codes(score(child(90), [check(temperature_c=38.6)]))


def test_neonate_keeps_n_rules_and_gets_infant_only_signs():
    res = score(child(10), [check(resp_rate=64, vomiting_everything=True)])
    assert {"N03", "I02"} <= codes(res) and "I05" not in codes(res)  # breathing judged by N03 in the first 28 days
    assert "N05" in codes(score(child(10), [check(temperature_c=37.5)]))
    nb = child(5)
    assert "N13" in {h["code"] for h in score_infant(nb, [], today=TODAY)["rule_hits"]}
    assert "N01" in codes(score(child(28), [check(not_feeding_well=True)]))
    assert "I01" in codes(score(child(29), [check(not_feeding_well=True)]))


# ---------------- weight-for-age (WHO table) ----------------
def test_wfa_table_median_and_minus2sd():
    med, sd = wfa_ref("m", 6)
    assert med == 7.9 and sd == pytest.approx(0.75)
    assert wfa_z("m", round(6 * T.DAYS_PER_MONTH), 7.9) == pytest.approx(0, abs=0.01)
    assert wfa_z("m", round(6 * T.DAYS_PER_MONTH), 6.4) == pytest.approx(-2.0, abs=0.02)
    med_f, _ = wfa_ref("f", 3)
    assert med_f == 5.8
    mid, _ = wfa_ref("m", 0.5)  # linear between month 0 (3.3) and month 1 (4.5)
    assert mid == pytest.approx(3.9)


def test_underweight_below_minus_2sd_is_yellow():
    days = round(6 * T.DAYS_PER_MONTH)
    low = score(child(days), [check(weight_g=6300)])
    assert "I10" in codes(low) and low["zone"] == "yellow"
    assert "I10" not in codes(score(child(days), [check(weight_g=6500)]))
    # the same weight is fine for a girl of that age (girls' -2 SD is 5.7 kg)
    assert "I10" not in codes(score(child(days, sex="f"), [check(weight_g=6300)]))


# ---------------- vaccines, cough, follow-up, feeding ----------------
def test_vaccine_overdue_after_30_days():
    birth = TODAY - timedelta(days=100)
    given = ["HepB-0", "BCG", "OPV-0"]
    assert set(overdue_vaccines(birth, given, TODAY)) == {"Penta-1", "OPV-1", "Rota-1", "PCV-1"}  # due day 61: 39 late
    assert overdue_vaccines(birth, given, birth + timedelta(days=91)) == []  # exactly 30 days late: not yet
    st = {v["code"]: v["status"] for v in vaccine_status(birth, given, TODAY)}
    assert st["BCG"] == "given" and st["Penta-2"] == "due" and st["MMR-1"] == "upcoming"
    res = score(child(100), [check(vaccines_given=given)])
    assert "I11" in codes(res) and res["zone"] == "yellow"


def test_cough_14_days_and_feeding_rules():
    assert "I12" in codes(score(child(120), [check(cough_days=14)]))
    assert "I12" not in codes(score(child(120), [check(cough_days=13)]))
    assert "I14" in codes(score(child(100), [check(feeding="mixed")]))
    assert "I14" in codes(score(child(100), [check(feeding="complementary")]))
    assert "I14" not in codes(score(child(200), [check(feeding="complementary")]))


def test_no_check_for_more_than_a_month():
    c = child(120)
    assert "I13" in codes(score_infant(c, [check(days_ago=31)], today=TODAY))
    assert "I13" not in codes(score_infant(c, [check(days_ago=30)], today=TODAY))
    assert "I13" not in codes(score_infant(c, [check(days_ago=31)], today=TODAY - timedelta(days=31)))


# ---------------- growth trends ----------------
def _series(c: dict, weights: list[tuple[int, int]]) -> list[dict]:
    return [check(days_ago=(TODAY - c["birth_date"]).days - age, weight_g=w) for age, w in weights]


def test_g01_z_score_falling():
    c = child(150)
    rows = _series(c, [(91, 6400), (122, 7000), (150, 6900)])  # z about 0 -> -0.9
    hits = growth_trend_hits(c, rows)
    assert "G01" in {h["code"] for h in hits}
    g = next(h for h in hits if h["code"] == "G01")
    assert g["values"][0] - g["values"][1] >= T.INF_Z_DROP and g["ages_months"] and g["direction"] == "down"
    assert "G01" not in {h["code"] for h in growth_trend_hits(c, _series(c, [(122, 7000), (150, 7400)]))}


def test_g02_weight_not_increasing_for_two_checks():
    c = child(210)
    hits = {h["code"]: h for h in growth_trend_hits(c, _series(c, [(152, 7600), (183, 7600), (210, 7550)]))}
    assert "G02" in hits and "o'sish to'xtashi" in hits["G02"]["uz_text"].lower()
    assert "G02" not in {h["code"] for h in growth_trend_hits(c, _series(c, [(152, 7600), (183, 7600), (210, 7700)]))}


def test_trends_need_a_week_between_checks():
    c = child(150)
    assert growth_trend_hits(c, _series(c, [(146, 7000), (150, 6300)])) == []


def test_trend_zone_combination():
    one = [{"code": "G01", "zone": "yellow"}]
    assert infant_trend_zone([], True) == "green"
    assert infant_trend_zone(one, False) == "yellow"
    assert infant_trend_zone(one, True) == "red"  # + any other yellow sign
    assert infant_trend_zone(one + [{"code": "G02", "zone": "yellow"}], False) == "red"


def test_growth_trend_plus_overdue_vaccine_is_red():
    c = child(150)
    rows = _series(c, [(91, 6400), (122, 7000), (150, 6900)])
    rows[-1]["vaccines_given"] = []
    for r in rows:
        r["vaccines_given"] = ["HepB-0", "BCG", "OPV-0"]
    res = score(c, rows)
    assert {"G01", "I11"} <= codes(res) and res["zone"] == "red" and res["trend_zone"] == "red"
    assert "QIZILga oshirildi" in res["explanation_uz"]
    only_trend = score(c, _series(c, [(91, 6400), (122, 7000), (150, 6900)]))
    assert only_trend["zone"] == "yellow"


def test_age_text():
    assert age_text(12) == "12 kun" and age_text(125) == "4 oy"
