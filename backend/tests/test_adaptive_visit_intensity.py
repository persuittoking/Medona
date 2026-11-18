"""Tests for Adaptive Visit Intensity (advisory only; mandatory 12 antenatal visits are NEVER reduced)."""
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import AuditLog, Pregnancy
from app.risk import thresholds as T
from app.services.visit_intensity import evaluate_eligibility, pregnancy_visit_plan
from tests.conftest import CHL, NUK, demo, login

TODAY = date(2026, 6, 1)


def _preg(weeks: float = 22.0, **over) -> dict:
    lmp = TODAY - timedelta(days=int(weeks * 7))
    d = {
        "lmp_date": lmp, "booking_date": lmp + timedelta(days=63), "birth_date": TODAY - timedelta(days=int(25 * 365.25)),
        "gravidity": 2, "parity": 1, "previous_cs": False, "hist_stillbirth": False, "hist_preterm": False,
        "miscarriages_count": 0, "hist_preeclampsia": False, "hist_pph": False, "diabetes": False,
        "chronic_htn": False, "heart": False, "kidney": False, "thyroid": False, "epilepsy": False,
        "multiple_pregnancy": False, "rh_negative": False, "interpregnancy_months": 36, "height_cm": 162.0,
        "booking_weight_kg": 58.0, "distance_to_perinatal_km": 8.0,
    }
    d.update(over)
    return d


def _visit(w: float, sys: int = 112, dia: int = 72, hb: float = 124.0) -> dict:
    return {
        "visit_date": TODAY - timedelta(days=int((24 - w) * 7)),
        "gestational_weeks": w, "systolic": sys, "diastolic": dia, "proteinuria": "neg",
        "hemoglobin_g_l": hb, "fasting_glucose_mmol": 4.4, "weight_kg": 58.0 + w * 0.25,
        "temperature_c": 36.6, "fetal_heart_rate": 140 if w >= 20 else None,
        "fundal_height_cm": w if w >= 20 else None, "symptoms": [],
    }


def _green_ra() -> dict:
    return {"zone": "green", "rule_hits": [], "trend_hits": []}


def test_thresholds_config_and_12_visits_never_reduced(monkeypatch):
    from app import config

    assert T.STANDARD_VISITS == 12
    assert len(T.STANDARD_VISIT_WEEKS) == 12
    assert T.CONSECUTIVE_GREEN_REQUIRED == 3
    assert T.LIGHT_VISIT_MAX_WEEKS == 36
    assert T.MINUTES_SAVED_PER_LIGHT_VISIT == 10

    # Even if PROPOSE_FEWER_VISITS=true in settings, total scheduled visits is ALWAYS 12
    real = config.get_settings()
    monkeypatch.setattr(config, "get_settings", lambda: real.model_copy(update={"propose_fewer_visits": True}))
    plan = evaluate_eligibility(
        _preg(22.0),
        [_visit(9), _visit(13), _visit(18), _visit(22)],
        [_green_ra(), _green_ra(), _green_ra(), _green_ra()],
        current_weeks=22.0,
        confirmed=True,
    )
    assert plan["standard_visits"] == 12
    assert plan["total_scheduled_visits"] == 12
    assert len(plan["schedule"]) == 12


def test_eligibility_rules_and_final_weeks_stay_full():
    vs = [_visit(9), _visit(13), _visit(18), _visit(22)]
    ras_4 = [_green_ra(), _green_ra(), _green_ra(), _green_ra()]

    # 1. Eligible with 4 consecutive green assessments, no risk factor, no trend, no alert, < 36 weeks
    ok = evaluate_eligibility(_preg(22.0), vs, ras_4, current_weeks=22.0, confirmed=False)
    assert ok["eligible"] is True and ok["confirmed"] is False
    assert ok["recommendation_uz"] == "Tavsiya: yengil ko'rik (oxirgi 4 ta natija yashil)"
    # Unconfirmed -> all active intensities stay "To'liq" (never automatic)
    assert all(sl["intensity"] == "To'liq" for sl in ok["schedule"])
    # From 36 weeks onwards (weeks 36, 38, 40), even recommended_intensity stays "To'liq"
    for sl in ok["schedule"]:
        if sl["target_week"] >= 36:
            assert sl["recommended_intensity"] == "To'liq"

    # 2. Fewer than 3 consecutive green assessments -> NOT eligible
    two_green = evaluate_eligibility(_preg(16.0), vs[:2], [_green_ra(), _green_ra()], current_weeks=16.0)
    assert two_green["eligible"] is False and two_green["recommendation_uz"] is None

    # 3. Tier B risk factor (e.g. Rh-negative Y12 or young/old age Y01) -> NOT eligible
    tier_b = evaluate_eligibility(_preg(22.0, rh_negative=True), vs, ras_4, current_weeks=22.0)
    assert tier_b["eligible"] is False and all(sl["recommended_intensity"] == "To'liq" for sl in tier_b["schedule"])

    # 4. Trend hit on latest assessment -> NOT eligible
    with_trend = ras_4[:-1] + [{"zone": "green", "rule_hits": [], "trend_hits": [{"code": "T01", "zone": "yellow"}]}]
    tr = evaluate_eligibility(_preg(22.0), vs, with_trend, current_weeks=22.0)
    assert tr["eligible"] is False

    # 5. Open alert -> NOT eligible
    al = evaluate_eligibility(_preg(22.0), vs, ras_4, has_open_alert=True, current_weeks=22.0)
    assert al["eligible"] is False

    # 6. Final weeks (>= 36 weeks) -> NOT eligible, all visits stay "To'liq"
    late = evaluate_eligibility(_preg(36.5), vs, ras_4, current_weeks=36.5)
    assert late["eligible"] is False and all(sl["recommended_intensity"] == "To'liq" for sl in late["schedule"])


@pytest.mark.parametrize("role,expected", [("nurse", 403), ("specialist", 403), ("department_head", 403)])
def test_only_doctor_can_confirm_light_visits(client, role, expected):
    pid, _ = demo("QQR-NUK-DEMO3")
    r = client.post(f"/api/patients/{pid}/visit-intensity/confirm", headers=login(client, NUK, role))
    assert r.status_code == expected


def test_doctor_confirms_demo3_and_dashboard_shows_saved_minutes_then_resets_on_yellow_or_red(client):
    pid, preg_id = demo("QQR-NUK-DEMO3")
    h_nurse = login(client, NUK, "nurse")
    h_doc = login(client, NUK, "doctor")

    # 1. Patient card shows "Tavsiya: yengil ko'rik (oxirgi 4 ta natija yashil)" and logs recommend_light_visit
    card = client.get(f"/api/patients/{pid}", headers=h_nurse).json()
    vp = card["visit_plan"]
    assert vp["standard_visits"] == 12 and len(vp["schedule"]) == 12
    assert vp["eligible"] is True and vp["confirmed"] is False
    assert vp["recommendation_uz"] == "Tavsiya: yengil ko'rik (oxirgi 4 ta natija yashil)"
    assert all(sl["intensity"] == "To'liq" for sl in vp["schedule"])

    with SessionLocal() as db:
        assert db.scalars(
            select(AuditLog).where(AuditLog.action == "recommend_light_visit", AuditLog.entity_id == preg_id)
        ).first() is not None

    # Another polyclinic's doctor gets 404
    assert client.post(f"/api/patients/{pid}/visit-intensity/confirm", headers=login(client, CHL, "doctor")).status_code == 404
    # Ineligible patient (DEMO1 is YELLOW) -> 409
    pid1, _ = demo("QQR-NUK-DEMO1")
    assert client.post(f"/api/patients/{pid1}/visit-intensity/confirm", headers=h_doc).status_code == 409

    # 2. Dashboard before confirming DEMO3
    before_sum = client.get("/api/dashboard/summary", headers=h_doc).json()["visit_intensity_impact"]
    assert before_sum["label_uz"] == "taxminiy, demo ma'lumot"

    # 3. Doctor confirms DEMO3
    conf = client.post(f"/api/patients/{pid}/visit-intensity/confirm", headers=h_doc)
    assert conf.status_code == 200, conf.text
    c_plan = conf.json()
    assert c_plan["confirmed"] is True and c_plan["confirmed_light_visits"] > 0
    assert c_plan["total_scheduled_visits"] == 12
    # Visits from 36 weeks onwards still stay "To'liq"
    assert all(sl["intensity"] == "To'liq" for sl in c_plan["schedule"] if sl["target_week"] >= 36)
    assert sum(1 for sl in c_plan["schedule"] if sl["intensity"] == "Yengil") == c_plan["confirmed_light_visits"]

    with SessionLocal() as db:
        assert db.scalars(
            select(AuditLog).where(AuditLog.action == "confirm_light_visit", AuditLog.entity_id == preg_id)
        ).first() is not None

    # 4. Dashboard impact panel increases by confirmed_light_visits * 10 min
    after_sum = client.get("/api/dashboard/summary", headers=h_doc).json()["visit_intensity_impact"]
    delta_visits = c_plan["confirmed_light_visits"]
    assert after_sum["confirmed_light_visits"] == before_sum["confirmed_light_visits"] + delta_visits
    assert after_sum["saved_doctor_minutes"] == after_sum["confirmed_light_visits"] * after_sum["minutes_per_light_visit"]

    # 5. New risk factor (Tier B rh_negative) immediately returns all remaining visits to "To'liq"
    with SessionLocal() as db:
        pr = db.get(Pregnancy, preg_id)
        pr.rh_negative = True
        pl_factor = pregnancy_visit_plan(db, pr)
        assert pl_factor["eligible"] is False and pl_factor["confirmed"] is False
        assert all(sl["intensity"] == "To'liq" for sl in pl_factor["schedule"])
        # Restore and re-confirm to test reset via a YELLOW/RED visit API call
        pr.rh_negative = False
        pr.light_visit_confirmed = True
        db.commit()

    # 6. A yellow/red visit immediately returns ALL remaining visits to "To'liq"
    v_res = client.post("/api/visits", headers=h_nurse, json={
        "pregnancy_id": preg_id, "systolic": 145, "diastolic": 92, "proteinuria": "neg", "hemoglobin_g_l": 118,
    })
    assert v_res.status_code == 201
    card_after = client.get(f"/api/patients/{pid}", headers=h_doc).json()
    vp_after = card_after["visit_plan"]
    assert vp_after["eligible"] is False and vp_after["confirmed"] is False
    assert vp_after["total_scheduled_visits"] == 12
    assert all(sl["intensity"] == "To'liq" for sl in vp_after["schedule"])
    with SessionLocal() as db:
        assert db.scalars(
            select(AuditLog).where(AuditLog.action == "reset_visit_intensity", AuditLog.entity_id == preg_id)
        ).first() is not None
