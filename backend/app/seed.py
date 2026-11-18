"""Reset and seed the database with SYNTHETIC demo data (multi-tenant by polyclinic).

Hierarchy: Region -> District -> Polyclinic (tenant) -> Mahalla -> Patients (home point inside the mahalla polygon).
Each mahalla gets 50-60 active pregnancies + 15-25 children aged 0-12 months (each linked to a delivered mother). Candidates are scored by the real risk
engine and kept by zone quota (ZONE_MIX), so every register shows a realistic green/yellow/red mix.
Usage (from backend/):  .venv\\Scripts\\python -m app.seed [--seed 7]
"""
from __future__ import annotations

import argparse
import time
from datetime import date, datetime, timedelta

import numpy as np

from app.db import Base, SessionLocal, engine
from app.geo import POLYCLINICS, REGIONS, haversine_km
from app.models import (
    Alert,
    AlertEvent,
    AuditLog,
    District,
    Mahalla,
    Newborn,
    NewbornCheck,
    Patient,
    Polyclinic,
    Pregnancy,
    Region,
    RiskAssessment,
    User,
    Visit,
    utcnow,
)
from app.risk import thresholds as T
from app.risk.engine import score_pregnancy
from app.risk.infant import score_infant, wfa_ref, wfa_z
from app.security.auth import hash_password
from app.security.crypto import encrypt, hash_pinfl
from app.services.alerts import record_event
from app.services.children import (
    apply_child_assessment,
    check_dict,
    check_extras,
    child_dict,
    make_child,
    mother_red_3rd_trimester,
    refresh_status,
    store_child_assessment,
)
from app.services.geo import check_patient_polyclinic, encrypt_home, sample_points, validate_home
from app.services.scoring import (
    apply_assessment,
    create_alert_if_worse,
    preg_dict,
    store_assessment,
    visit_dict,
)
from ml.generate_synthetic import make_pregnancy, make_visits
from seed.fetch_mahallas import as_shape
from seed.fetch_mahallas import load as load_boundary

DEMO_PASSWORD = "demo1234"
# Realistic size of one mahalla's antenatal register (one mahalla per demo polyclinic).
ACTIVE_PER_MAHALLA = (50, 60)    # active pregnancies, inclusive range
CHILDREN_PER_MAHALLA = (15, 25)  # children 0-12 months (each with a delivered mother), inclusive range
DEMO_ACTIVE_ZONES = {"yellow": 2, "green": 1}  # DEMO1-2 yellow, DEMO3 green (PL-NUK-001); DEMO4 is delivered
# Demo register zone mix (product target for a realistic-looking dashboard, NOT an epidemiological estimate):
# each mahalla's quota is drawn inside these bands and candidates are accepted by their computed zone.
ZONE_MIX = {"red": (0.03, 0.07), "yellow": (0.20, 0.28)}
MAX_DRAWS_PER_MAHALLA = 3000
ACTIONS = [
    "Bemor bilan telefon orqali bog'lanildi, perinatal markazga yo'llandi",
    "Arterial bosim qayta o'lchandi, shifokor ko'rigiga chaqirildi",
    "Gemoglobin tahlili qayta topshirildi, temir preparatlari bo'yicha ko'rik belgilandi",
    "Patronaj hamshirasi uyga yuborildi",
    "UTT va KTG tekshiruviga yo'llanma berildi",
]
PREG_KEYS = [
    "lmp_date", "booking_date", "gravidity", "parity", "previous_cs", "hist_stillbirth", "hist_preterm",
    "miscarriages_count", "hist_preeclampsia", "hist_pph", "diabetes", "chronic_htn", "heart", "kidney",
    "thyroid", "epilepsy", "multiple_pregnancy", "rh_negative", "interpregnancy_months", "height_cm",
    "booking_weight_kg",
]


class Tenant:
    """Seed-time context of one polyclinic: its mahalla(s), staff and a pool of home points inside each polygon."""

    def __init__(self, db, rng, pdef: dict, rdef: dict, ddef: dict, district: District, pw: str):
        from shapely.ops import unary_union

        self.pdef, self.rdef, self.ddef, self.district = pdef, rdef, ddef, district
        keys = pdef.get("mahalla_keys") or [pdef["mahalla_key"]]
        feats = [load_boundary(k) for k in keys]
        polys = [as_shape(f) for f in feats]
        centre = unary_union(polys).centroid
        self.polyclinic = Polyclinic(code=pdef["code"], name=pdef["name"], district_id=district.id,
                                     address=pdef["address"], lat=round(centre.y, 6), lon=round(centre.x, 6))
        db.add(self.polyclinic)
        db.flush()
        self.mahallas: list[Mahalla] = []
        self.nurses: list[User] = []
        self._homes_by_m: list[list[tuple[float, float]]] = []
        self._home_i_by_m: list[int] = []
        self.users: dict[str, User] = {}
        for i, (feat, poly) in enumerate(zip(feats, polys, strict=True)):
            props = feat["properties"]
            m = Mahalla(name=props["name"], polyclinic_id=self.polyclinic.id, boundary_geojson=feat["geometry"],
                        boundary_source=props["source"], demo_boundary=bool(props.get("demo_boundary", True)),
                        centroid_lat=round(poly.centroid.y, 6), centroid_lon=round(poly.centroid.x, 6))
            db.add(m)
            db.flush()
            self.mahallas.append(m)
            uname = "nurse" if i == 0 else f"nurse{i + 1}"
            label = f"Patronaj hamshirasi ({m.name})" if len(feats) > 1 else f"Patronaj hamshirasi ({pdef['code']})"
            u = User(username=uname, full_name=label, role="nurse", polyclinic_id=self.polyclinic.id,
                     mahalla_id=m.id, district_id=district.id, region_id=district.region_id, password_hash=pw)
            db.add(u)
            self.nurses.append(u)
            self.users[uname] = u
            self._homes_by_m.append(sample_points(feat["geometry"], 350, rng))
            self._home_i_by_m.append(0)
        for role, title in [("doctor", "Oilaviy shifokor"),
                            ("specialist", "OvaBMU mutaxassisi"), ("department_head", "OvaBMU bo'lim mudiri")]:
            u = User(username=role, full_name=f"{title} ({pdef['code']})", role=role, polyclinic_id=self.polyclinic.id,
                     district_id=district.id, region_id=district.region_id, password_hash=pw)
            db.add(u)
            self.users[role] = u
        db.flush()
        self._m_idx = 0
        self.mahalla = self.mahallas[0]
        self._seq = 400

    def use_mahalla(self, idx: int) -> None:
        self._m_idx = idx
        self.mahalla = self.mahallas[idx]
        self.users["nurse"] = self.nurses[idx]

    def next_code(self) -> int:
        self._seq += 1
        return self._seq

    def next_home_distance_km(self) -> float:
        """Distance to the perinatal centre of the home point the next add_patient() will use."""
        idx = self._m_idx
        lat, lon = self._homes_by_m[idx][self._home_i_by_m[idx]]
        per = self.rdef["perinatal"]
        return round(haversine_km(lat, lon, per["lat"], per["lon"]), 1)

    def add_patient(self, db, p: dict) -> Patient:
        idx = self._m_idx
        lat, lon = self._homes_by_m[idx][self._home_i_by_m[idx]]
        self._home_i_by_m[idx] += 1
        validate_home(self.mahalla.boundary_geojson, lat, lon)
        per = self.rdef["perinatal"]
        pat = Patient(code=p["code"], full_name_enc=encrypt(p["full_name"]), pinfl_enc=encrypt(p["pinfl"]),
                      pinfl_hash=hash_pinfl(p["pinfl"]),
                      phone_enc=encrypt(p["phone"]), home_enc=encrypt_home(lat, lon), birth_date=p["birth_date"],
                      polyclinic_id=self.mahalla.polyclinic_id, mahalla_id=self.mahalla.id,
                      distance_to_perinatal_km=round(haversine_km(lat, lon, per["lat"], per["lon"]), 1),
                      assigned_nurse_id=self.nurses[idx].id)
        db.add(pat)
        db.flush()
        check_patient_polyclinic(db, pat)
        return pat


def _add_pregnancy(db, pat: Patient, preg: dict, status: str = "active") -> Pregnancy:
    pr = Pregnancy(patient_id=pat.id, status=status, **{k: preg[k] for k in PREG_KEYS})
    db.add(pr)
    db.flush()
    db.refresh(pr)
    return pr


def _settle_alert(db, rng, alert: Alert | None, at: datetime, days_ago: int, actions: list[str],
                  keep_open: bool = False) -> None:
    """Older alerts were handled (resolved); recent ones are open or acknowledged (50/50) — demo realism."""
    if alert is None or keep_open:
        return
    if days_ago > 2:
        alert.acknowledged_at = at + timedelta(minutes=int(rng.integers(15, 240)))
        alert.status = "resolved"
        alert.resolved_at = alert.acknowledged_at
        alert.action_taken = str(rng.choice(actions))
        record_event(db, alert, "acknowledged", assignee_id=alert.assigned_user_id,
                     actor_id=alert.assigned_user_id, at=alert.acknowledged_at)
        record_event(db, alert, "resolved", assignee_id=alert.assigned_user_id,
                     actor_id=alert.assigned_user_id, note=alert.action_taken, at=alert.resolved_at)
    elif rng.random() < 0.5:
        alert.acknowledged_at = at + timedelta(minutes=int(rng.integers(10, 90)))
        alert.status = "acknowledged"
        alert.measurement_due_at = alert.acknowledged_at + timedelta(hours=T.MEASUREMENT_DUE_HOURS[alert.level])
        alert.action_taken = str(rng.choice(actions))
        record_event(db, alert, "acknowledged", assignee_id=alert.assigned_user_id,
                     actor_id=alert.assigned_user_id, note=alert.action_taken, at=alert.acknowledged_at)


def _score_history(db, rng, pr: Pregnancy, visits: list[dict], nurse: User | None, today: date) -> None:
    """Insert visits chronologically, scoring each one as if entered on that day."""
    zone, probs, hist = "green", [], []
    for v in visits:
        row = Visit(pregnancy_id=pr.id, entered_by=nurse.id if nurse else None, notes=v.get("notes"),
                    **visit_dict(v))
        db.add(row)
        db.flush()
        hist.append(visit_dict(v))
        res = score_pregnancy(preg_dict(pr), hist, prev_ml_prob=probs[-1] if probs else None,
                              prev_ml_probs=probs[-2:] or None)
        at = datetime.combine(v["visit_date"], datetime.min.time()) + timedelta(hours=5, minutes=int(rng.integers(0, 300)))
        at = min(at, utcnow() - timedelta(minutes=5))  # never in the future
        row.created_at = at  # saved "on that day" (closed-loop evidence and quality signals use created_at)
        ra = store_assessment(db, pr, row, res, created_at=at)
        alert = create_alert_if_worse(db, pr, zone, ra, now=at)
        _settle_alert(db, rng, alert, at, (today - v["visit_date"]).days, ACTIONS)
        zone = ra.zone
        probs.append(ra.ml_probability)
        apply_assessment(pr, ra)


def _demo_patients(db, rng, t: Tenant, today: date) -> None:
    nurse = t.users["nurse"]

    def base(code, name, age, weeks, **preg_over):
        lmp = today - timedelta(days=int(weeks * 7))
        birth = lmp - timedelta(days=int(age * 365.25) + 30)
        p = {"code": code, "full_name": name, "pinfl": f"4{birth:%d%m%y}{rng.integers(1000000, 9999999)}",
             "phone": "+99890" + str(rng.integers(1000000, 9999999)), "birth_date": birth}
        preg = {"lmp_date": lmp, "booking_date": lmp + timedelta(days=70), "gravidity": 1, "parity": 0,
                "previous_cs": False, "hist_stillbirth": False, "hist_preterm": False, "miscarriages_count": 0,
                "hist_preeclampsia": False, "hist_pph": False, "diabetes": False, "chronic_htn": False,
                "heart": False, "kidney": False, "thyroid": False, "epilepsy": False,
                "multiple_pregnancy": False, "rh_negative": False, "interpregnancy_months": None,
                "height_cm": 162.0, "booking_weight_kg": 58.0, **preg_over}
        pat = t.add_patient(db, p)
        return pat, _add_pregnancy(db, pat, preg), lmp

    def v(lmp, w, s, d, hb, wt, prot="neg", glu=4.4, fundal=None, syms=(), fhr=None):
        return {"visit_date": lmp + timedelta(days=int(round(w * 7))), "gestational_weeks": w, "systolic": s,
                "diastolic": d, "proteinuria": prot, "hemoglobin_g_l": hb, "fasting_glucose_mmol": glu,
                "weight_kg": wt, "temperature_c": 36.6, "fetal_heart_rate": fhr if fhr else (142 if w >= 20 else None),
                "fundal_height_cm": fundal if fundal is not None else (round(w - 0.5, 1) if w >= 20 else None),
                "symptoms": list(syms)}

    # DEMO1 — "Dilnoza", 19 y, first pregnancy, 31 weeks: BP rising at every one of the last 3 checkups
    # (116/72 -> 121/78 -> 127/84; diastolic +3 mmHg/week -> projected 90 in 2 weeks) while every single value is
    # still below 140/90 and 130/85 -> YELLOW by the predictive trend rule P01 only. Hb drifting down (118 -> 109,
    # not fast enough for P02), fundal height slightly behind (2.3 cm, below T04).
    # Live demo: new visit BP 152/98, proteinuria +2, severe headache -> RED (R02).
    _, p1, lmp = base("QQR-NUK-DEMO1", "Dilnoza Karimova", 19, 31.3)
    _score_history(db, rng, p1, [
        v(lmp, 10.0, 112, 72, 121, 58.0),
        v(lmp, 16.3, 114, 74, 120, 59.8),
        v(lmp, 22.3, 114, 72, 119, 62.0),
        v(lmp, 25.3, 116, 72, 118, 63.4),
        v(lmp, 27.3, 121, 78, 113, 64.6),
        v(lmp, 29.3, 127, 84, 109, 65.6, fundal=27.0, syms=["edema"]),
    ], nurse, today)
    if p1.current_zone != "yellow":
        print(f"WARNING: DEMO1 should be YELLOW before the live demo but is {p1.current_zone.upper()} "
              "(model retrained?). Adjust its history in app/seed.py.")

    # DEMO2 — 37 y, previous caesarean, GDM glucose 5.6 -> stable YELLOW (explainability).
    _, p2, lmp = base("QQR-NUK-DEMO2", "Gulnora Rahimova", 37, 27.0, gravidity=3, parity=2, previous_cs=True,
                      interpregnancy_months=40, booking_weight_kg=66.0)
    _score_history(db, rng, p2, [
        v(lmp, 9.5, 114, 74, 124, 66.0, glu=4.8),
        v(lmp, 19.0, 116, 74, 121, 69.0, glu=4.9),
        v(lmp, 25.0, 116, 76, 119, 72.0, glu=5.6),
    ], nurse, today)

    # DEMO3 — healthy pregnancy -> GREEN (the system does not over-alarm; 4 green visits -> eligible for "Yengil").
    _, p3, lmp = base("QQR-NUK-DEMO3", "Madina Yusupova", 26, 24.0, gravidity=2, parity=1,
                      interpregnancy_months=38, booking_weight_kg=57.0)
    _score_history(db, rng, p3, [
        v(lmp, 9.0, 110, 70, 128, 57.0),
        v(lmp, 13.5, 111, 70, 127, 58.0),
        v(lmp, 18.0, 112, 70, 126, 59.5),
        v(lmp, 22.5, 110, 72, 124, 61.6),
    ], nurse, today)

    # DEMO4 — delivered: newborn with low birth weight + fast breathing -> newborn RED.
    _, p4, lmp = base("QQR-NUK-DEMO4", "Shahnoza Ergasheva", 23, 39.5)
    p4.status, p4.current_zone = "delivered", "yellow"
    _score_history(db, rng, p4, [v(lmp, 11.0, 112, 70, 116, 58.0), v(lmp, 30.0, 120, 78, 108, 66.0)], nurse, today)
    b4 = today - timedelta(days=4)
    _seed_child(db, rng, t, p4, today, b4, 36.0, 2150, 8, "f", [
        {"check_date": b4 + timedelta(days=1), "resp_rate": 52, "temperature_c": 36.8, "weight_g": 2110,
         "feeding": "exclusive_breast", "vaccines_given": ["HepB-0"]},
        {"check_date": today - timedelta(days=1), "resp_rate": 64, "temperature_c": 36.9, "weight_g": 2080,
         "feeding": "exclusive_breast", "vaccines_given": ["BCG", "OPV-0"]},
    ], keep_open=True)

    # DEMO5 — healthy boy, ~4 months, all checks normal and vaccines on time -> GREEN.
    # Live demo ("Bolalar"): new check with breathing 56/min -> RED by I05 (>= 50/min from 2 months; the same 56/min
    # would NOT be fast breathing under 2 months, where the limit is 60).
    _, p5, lmp5 = base("QQR-NUK-DEMO5", "Zarina Qodirova", 25, 39.0 + 125 / 7, gravidity=2, parity=1,
                       interpregnancy_months=36)
    p5.status = "delivered"
    _score_history(db, rng, p5, [v(lmp5, 11.0, 110, 70, 124, 58.0), v(lmp5, 24.0, 112, 72, 120, 63.0),
                                 v(lmp5, 36.0, 114, 72, 118, 68.0)], nurse, today)
    b5 = today - timedelta(days=125)
    rows5, given = [], []
    for d, wt in ((3, 3350), (14, 3900), (30, 4700), (61, 5650), (91, 6450), (122, 7050)):
        doses = [c for c, _, due in T.VACCINE_SCHEDULE if due <= d and c not in given]
        given += doses
        rows5.append({"check_date": b5 + timedelta(days=d), "weight_g": wt, "resp_rate": 46 if d < 60 else 38,
                      "temperature_c": 36.7, "feeding": "exclusive_breast", "vaccines_given": doses})
    _seed_child(db, rng, t, p5, today, b5, 39.3, 3450, 9, "m", rows5)


# Trend-only demo patients (per polyclinic): a clear 3-checkup trend while the last visit is still below every
# static threshold, so the demo shows "yellow/red by trend only". (code suffix, name, age, current week, expected zone)
TREND_DEMO_ZONES = {"yellow": 2, "red": 1}


def _trend_demo_patients(db, rng, t: Tenant, today: date) -> None:
    nurse = t.users["nurse"]
    prefix = f"{t.rdef['code']}-{t.ddef['code']}"

    def add(suffix: str, name: str, age: float, weeks: float, height: float, weight: float,
            rows: list[tuple[float, int, int, float, float]], open_alert: bool = False) -> None:
        lmp = today - timedelta(days=int(round(weeks * 7)))
        birth = lmp - timedelta(days=int(age * 365.25) + 30)
        pat = t.add_patient(db, {"code": f"{prefix}-{suffix}", "full_name": name, "birth_date": birth,
                                 "pinfl": f"4{birth:%d%m%y}{rng.integers(1000000, 9999999)}",
                                 "phone": "+99891" + str(rng.integers(1000000, 9999999))})
        pr = _add_pregnancy(db, pat, {
            "lmp_date": lmp, "booking_date": lmp + timedelta(days=70), "gravidity": 2, "parity": 1,
            "previous_cs": False, "hist_stillbirth": False, "hist_preterm": False, "miscarriages_count": 0,
            "hist_preeclampsia": False, "hist_pph": False, "diabetes": False, "chronic_htn": False, "heart": False,
            "kidney": False, "thyroid": False, "epilepsy": False, "multiple_pregnancy": False, "rh_negative": False,
            "interpregnancy_months": 38, "height_cm": height, "booking_weight_kg": weight})
        visits = [{"visit_date": lmp + timedelta(days=int(round(w * 7))), "gestational_weeks": w, "systolic": s,
                   "diastolic": d, "proteinuria": "neg", "hemoglobin_g_l": hb, "fasting_glucose_mmol": 4.5,
                   "weight_kg": wt, "temperature_c": 36.6, "fetal_heart_rate": 140 if w >= 20 else None,
                   "fundal_height_cm": round(w - 0.5, 1) if w >= 20 else None, "symptoms": []}
                  for w, s, d, hb, wt in rows]
        _score_history(db, rng, pr, visits, nurse, today)
        if open_alert:  # keep the newest (trend-driven) alert open for the alert inbox demo
            last = db.query(Alert).filter_by(pregnancy_id=pr.id).order_by(Alert.id.desc()).first()
            if last is not None:
                last.status, last.acknowledged_at, last.resolved_at, last.action_taken = "open", None, None, None
                db.query(AlertEvent).filter(AlertEvent.alert_id == last.id, AlertEvent.event != "created").delete()

    # TRND1: diastolic 72 -> 78 -> 84 (+3/week, projected 90) with 121/84 now -> P01 YELLOW
    add("TRND1", "Nilufar Saidova", 27, 31.0, 160.0, 60.0, [
        (10.0, 110, 68, 124, 60.0), (20.0, 112, 70, 122, 64.0), (26.0, 112, 72, 121, 66.6),
        (28.0, 116, 78, 120, 67.4), (30.0, 121, 84, 119, 68.2)])
    # TRND2: systolic 116 -> 125 -> 134 (+3/week, projected 140) and already >= 130 -> P01 RED (no static rule)
    add("TRND2", "Feruza Aliyeva", 29, 30.15, 163.0, 61.0, [
        (10.0, 112, 70, 125, 61.0), (18.0, 114, 72, 123, 64.0), (24.0, 116, 74, 122, 66.4),
        (27.0, 125, 79, 121, 67.6), (30.0, 134, 84, 120, 68.8)], open_alert=True)
    # TRND3: Hb 122 -> 113 -> 104 g/L (-2.25/week, projected 99.5) while still >= 100 -> P02 YELLOW
    add("TRND3", "Sevara Tursunova", 24, 29.0, 158.0, 56.0, [
        (10.0, 108, 68, 126, 56.0), (16.0, 110, 70, 124, 58.0), (20.0, 110, 70, 122, 60.0),
        (24.0, 108, 68, 113, 62.0), (28.0, 110, 70, 104, 64.0)])


# ---------------- children 0-12 months ----------------
CHILD_ACTIONS = [
    "Ona bilan telefon orqali bog'lanildi, bola pediatr ko'rigiga chaqirildi",
    "Patronaj hamshirasi bolani uyda ko'rdi, emizish bo'yicha maslahat berildi",
    "Bola bolalar shifoxonasiga yo'llandi",
    "Kechikkan emlashlar uchun emlash xonasiga yozildi",
    "Vazn 7 kun ichida qayta o'lchanadi",
]
CHECK_DAYS = [1, 3, 7, 14, 30, 61, 91, 122, 152, 183, 213, 244, 274, 305, 335]
# Demo profile mix of the synthetic children (NOT epidemiology): most follow a normal growth curve.
CHILD_PROFILES = {"normal": 0.71, "falter": 0.07, "acute": 0.04, "stale": 0.07, "vaccine_miss": 0.05, "mixed_feed": 0.06}


def _child_check_rows(nb_birth: date, sex: str, bw: int, today: date, rng, profile: str) -> list[dict]:
    """Synthetic infant checks: WHO-curve weight with a child-specific z-track, profile-specific problems."""
    age = (today - nb_birth).days
    days = []
    for d in CHECK_DAYS:
        d = d + (int(rng.integers(-3, 4)) if d > 14 else 0)
        if d <= age and (not days or d - days[-1] >= 2):
            days.append(d)
    if profile == "stale" and age > 75:
        cut = age - int(rng.integers(40, 60))
        days = [d for d in days if d <= cut] or days[:2]
    days = days[-6:]
    z_birth = float(np.clip(wfa_z(sex, 0, bw / 1000), -2.5, 2.5))
    z_track = float(np.clip(rng.normal(0.0, 0.55), -1.4, 1.6))
    rows, zs = [], []
    for i, d in enumerate(days):
        z = z_track + (z_birth - z_track) * np.exp(-d / 45) + float(rng.normal(0, 0.06))
        if d <= 7:  # physiological weight loss in the first week
            z -= 0.35
        zs.append(z)
        med, sd = wfa_ref(sex, d / 30.4375)
        w = med + z * sd
        last = i == len(days) - 1
        if profile == "falter" and last and len(rows) >= 2 and d - days[i - 1] >= 7:
            if rng.random() < 0.7:  # G01: z-score falls
                w = med + (zs[i - 1] - float(rng.uniform(0.75, 1.0))) * sd
            else:  # G02: weight stops increasing at two checks
                rows[-1]["weight_g"] = rows[-2]["weight_g"] + int(rng.integers(-60, 20))
                w = (rows[-1]["weight_g"] - int(rng.integers(0, 80))) / 1000
        m = d / 30.4375
        young = d < 60
        rows.append({
            "check_date": nb_birth + timedelta(days=d), "weight_g": int(round(w * 1000)),
            "length_cm": round(49.5 + 3.6 * min(m, 3) + 1.6 * max(0.0, min(m, 6) - 3) + 1.1 * max(0.0, m - 6)
                               + float(rng.normal(0, 0.6)), 1),
            "head_circ_cm": round(34.3 + 1.9 * min(m, 3) + 0.8 * max(0.0, min(m, 6) - 3) + 0.4 * max(0.0, m - 6)
                                  + float(rng.normal(0, 0.4)), 1),
            "resp_rate": int(rng.integers(38, 56) if young else rng.integers(28, 44)),
            "temperature_c": round(float(rng.normal(36.7, 0.2)), 1),
            "feeding": ("complementary" if d >= 183 else
                        ("mixed" if profile == "mixed_feed" else ("exclusive_breast" if rng.random() < 0.96 else "mixed"))),
            "vaccines_given": [], "diarrhoea_days": None, "cough_days": None,
        })
    # vaccines: due doses are given at the first check on/after their due day (vaccine_miss: the 2-month doses not)
    given: set[str] = set()
    for r in rows:
        d = (r["check_date"] - nb_birth).days
        for code, _, due in T.VACCINE_SCHEDULE:
            skip = profile == "vaccine_miss" and due == 61
            if due <= d and code not in given and not skip and rng.random() < 0.97:
                r["vaccines_given"].append(code)
                given.add(code)
    if profile == "acute" and rows:
        last, d = rows[-1], (rows[-1]["check_date"] - nb_birth).days
        sign = str(rng.choice(["breathing", "diarrhoea", "blood", "vomiting", "fever" if d < 60 else "breathing"]))
        if sign == "breathing":
            last["resp_rate"] = (T.INF_RESP_FAST_UNDER_2M if d < 60 else T.INF_RESP_FAST_2_12M) + int(rng.integers(2, 9))
            last["cough_days"] = int(rng.integers(2, 6))
        elif sign == "diarrhoea":
            last["diarrhoea_days"] = int(rng.integers(14, 19))
        elif sign == "blood":
            last["blood_in_stool"], last["diarrhoea_days"] = True, int(rng.integers(2, 5))
        elif sign == "vomiting":
            last["vomiting_everything"] = True
        else:
            last["temperature_c"] = round(float(rng.uniform(38.1, 38.8)), 1)
    return rows


def _seed_child(db, rng, t: Tenant, pr: Pregnancy, today: date, birth: date, ga: float, bw: int, apgar: int,
                sex: str, checks: list[dict], keep_open: bool = False) -> Newborn:
    """Register a child and score each check as if entered on that day (the last one as of today)."""
    nb = make_child(db, pr, birth_date=birth, ga=ga, birth_weight_g=bw, apgar_5=apgar, sex=sex)
    mother_red = mother_red_3rd_trimester(db, pr.id)
    nurse = t.users["nurse"]
    zone, prior = "green", []
    for i, ck in enumerate(checks or [None]):
        last = i == len(checks) - 1 or not checks
        row = None
        if ck is not None:
            row = NewbornCheck(newborn_id=nb.id, entered_by=nurse.id, **ck, **check_extras(nb, ck, prior))
            db.add(row)
            db.flush()
            prior.append(row)
        on = today if last else ck["check_date"]
        res = score_infant(child_dict(nb), [check_dict(c) for c in prior], today=on,
                           mother_red_3rd_trimester=mother_red)
        day = ck["check_date"] if ck is not None else today
        at = datetime.combine(day, datetime.min.time()) + timedelta(hours=5, minutes=int(rng.integers(0, 300)))
        if last and (today - day).days > T.INF_CHECK_INTERVAL_DAYS:
            at = datetime.combine(today, datetime.min.time())  # the "no check for > 30 days" sign is from today
        at = min(at, utcnow() - timedelta(minutes=5))
        if row is not None:
            row.created_at = at
        ra = store_child_assessment(db, nb, row, res, created_at=at)
        alert = create_alert_if_worse(db, nb, zone, ra, now=at)
        _settle_alert(db, rng, alert, at, (today - day).days, CHILD_ACTIONS, keep_open=keep_open and last)
        zone = ra.zone
        apply_child_assessment(nb, ra)
    refresh_status(nb, today)
    return nb


def _random_child(db, rng, t: Tenant, today: date) -> None:
    """A delivered mother (full synthetic antenatal history) + her child aged 4-364 days."""
    age = int(rng.integers(4, 365))
    birth = today - timedelta(days=age)
    cand = _draw_candidate(rng, t, birth, delivered=True)
    p, preg, visits, cur_w = cand
    pat = t.add_patient(db, p)
    pr = _add_pregnancy(db, pat, preg, status="delivered")
    _score_history(db, rng, pr, visits, t.users["nurse"], today)
    ga = round(min(cur_w, 41.0), 1) if rng.random() > 0.08 else round(float(rng.uniform(33.0, 36.9)), 1)
    bw = int(np.clip(rng.normal(3300 - max(0, 39 - ga) * 220, 400), 1600, 4600))
    sex = "m" if rng.random() < 0.51 else "f"
    profile = str(rng.choice(list(CHILD_PROFILES), p=list(CHILD_PROFILES.values())))
    _seed_child(db, rng, t, pr, today, birth, ga, bw, int(rng.integers(7, 10)), sex,
                _child_check_rows(birth, sex, bw, today, rng, profile))


def _final_zone(preg: dict, visits: list[dict]) -> str:
    """Zone after the last visit, scored visit by visit exactly as _score_history does (pure, no DB)."""
    probs, res = [], None
    for k in range(len(visits)):
        res = score_pregnancy(preg, [visit_dict(v) for v in visits[: k + 1]],
                              prev_ml_prob=probs[-1] if probs else None, prev_ml_probs=probs[-2:] or None)
        probs.append(res["ml_probability"])
    return res["zone"]


def _draw_candidate(rng, t: Tenant, today: date, delivered: bool) -> tuple[dict, dict, list[dict], float]:
    """A synthetic pregnancy (not yet in the DB): patient dict, pregnancy dict, visits, current week."""
    while True:
        cur_w = float(rng.uniform(38, 41)) if delivered else float(rng.uniform(7, 40.5))
        lmp = today - timedelta(days=int(cur_w * 7))
        p, preg, lat = make_pregnancy(rng, t.rdef, t.ddef, t.next_code(), lmp)
        if (preg["booking_date"] - lmp).days / 7 <= cur_w:
            break  # otherwise: not booked yet, draw again
    last_visit_w = max((preg["booking_date"] - lmp).days / 7, cur_w - float(rng.uniform(0, 3.5)))
    # Demo enrichment (documented): some currently-deteriorating cases so the dashboard is not empty.
    if cur_w > 24 and rng.random() < 0.04:
        lat.pe_onset, lat.pe_rate = cur_w - float(rng.uniform(3, 8)), float(rng.uniform(3.5, 6.5))
    elif cur_w > 18 and rng.random() < 0.04:
        lat.anemia_onset, lat.anemia_rate = cur_w - float(rng.uniform(6, 14)), float(rng.uniform(2.0, 3.5))
    preg["distance_to_perinatal_km"] = t.next_home_distance_km()  # the real home point, as stored in the DB
    visits = make_visits(rng, preg, lat, upto_w=min(last_visit_w, lat.delivery_week + 1))
    return p, preg, visits, cur_w


def _insert_pregnancy(db, rng, t: Tenant, today: date, cand: tuple, delivered: bool) -> None:
    p, preg, visits, cur_w = cand
    pat = t.add_patient(db, p)
    pr = _add_pregnancy(db, pat, preg, status="delivered" if delivered else "active")
    _score_history(db, rng, pr, visits, t.users["nurse"], today)


def zone_quotas(rng, n_active: int) -> dict[str, int]:
    """Target zone mix of one mahalla register, drawn inside ZONE_MIX (demo sampling, not epidemiology)."""
    red = int(round(n_active * rng.uniform(*ZONE_MIX["red"])))
    yellow = int(round(n_active * rng.uniform(*ZONE_MIX["yellow"])))
    return {"red": red, "yellow": yellow, "green": n_active - red - yellow}


def _fill_register(db, rng, t: Tenant, today: date, quotas: dict[str, int]) -> None:
    """Draw candidates, score them in memory and keep each one while its zone still has room (quota sampling).

    After MAX_DRAWS_PER_MAHALLA candidates any zone is accepted, so seeding always terminates.
    """
    left, draws = dict(quotas), 0
    while sum(left.values()) > 0:
        cand = _draw_candidate(rng, t, today, delivered=False)
        draws += 1
        _, preg, visits, _ = cand
        zone = _final_zone(preg, visits)
        if left[zone] <= 0 and draws < MAX_DRAWS_PER_MAHALLA:
            continue
        if left[zone] <= 0:  # give up on the exact mix, take the zone that still needs the most
            zone = max(left, key=left.get)
        left[zone] -= 1
        _insert_pregnancy(db, rng, t, today, cand, delivered=False)


def reset_schema() -> None:
    """Drop EVERY existing table (also ones from older schema versions) and recreate the current schema."""
    from sqlalchemy import MetaData, text

    with engine.begin() as conn:
        if engine.dialect.name == "sqlite":
            conn.execute(text("PRAGMA foreign_keys=OFF"))
        old = MetaData()
        old.reflect(bind=conn)
        old.drop_all(bind=conn)
        if engine.dialect.name == "sqlite":
            conn.execute(text("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)


def seed(seed_value: int = 7, active_per_mahalla: tuple[int, int] = ACTIVE_PER_MAHALLA,
         children_per_mahalla: tuple[int, int] = CHILDREN_PER_MAHALLA) -> dict:
    """Reset the DB and seed it. Tests pass a smaller `active_per_mahalla` for speed."""
    t0 = time.time()
    rng = np.random.default_rng(seed_value)
    today = date.today()
    reset_schema()
    pw = hash_password(DEMO_PASSWORD)
    with SessionLocal() as db:
        tenants: dict[str, Tenant] = {}
        for rdef in REGIONS:
            region = Region(code=rdef["code"], name=rdef["name"], lat=rdef["lat"], lon=rdef["lon"])
            db.add(region)
            db.flush()
            for ddef in rdef["districts"]:
                d = District(region_id=region.id, code=ddef["code"], name=ddef["name"], lat=ddef["lat"], lon=ddef["lon"])
                db.add(d)
                db.flush()
                for pdef in POLYCLINICS:
                    if pdef["region"] == rdef["code"] and pdef["district"] == ddef["code"]:
                        tenants[pdef["code"]] = Tenant(db, rng, pdef, rdef, ddef, d, pw)
                if rdef["code"] == "QQR" and ddef["code"] == "NUK":
                    db.add(User(username="district.admin", full_name=f"{d.name} tibbiyot birlashmasi",
                                role="district_admin", district_id=d.id, region_id=region.id, password_hash=pw))
                if rdef["code"] == "SAM" and ddef["code"] == "SAM":
                    db.add(User(username="sam.district.admin", full_name=f"{d.name} tibbiyot birlashmasi",
                                role="district_admin", district_id=d.id, region_id=region.id, password_hash=pw))
            if rdef["code"] == "QQR":
                db.add(User(username="region.admin", full_name=f"{rdef['name']} sog'liqni saqlash vazirligi",
                            role="region_admin", region_id=region.id, password_hash=pw))
            if rdef["code"] == "SAM":
                db.add(User(username="sam.region.admin", full_name=f"{rdef['name']} sog'liqni saqlash boshqarmasi",
                            role="region_admin", region_id=region.id, password_hash=pw))
        db.flush()

        for t in tenants.values():
            for m_idx in range(len(t.mahallas)):
                t.use_mahalla(m_idx)
                quotas = zone_quotas(rng, int(rng.integers(active_per_mahalla[0], active_per_mahalla[1] + 1)))
                if m_idx == 0:
                    if t.pdef["code"] == "PL-NUK-001":
                        for z, k in DEMO_ACTIVE_ZONES.items():  # DEMO1-3 are added below and count towards the mix
                            quotas[z] -= k
                    for z, k in TREND_DEMO_ZONES.items():  # TRND1-3 too
                        quotas[z] = max(0, quotas[z] - k)
                _fill_register(db, rng, t, today, quotas)
                if m_idx == 0:
                    _trend_demo_patients(db, rng, t, today)
                for _ in range(int(rng.integers(children_per_mahalla[0], children_per_mahalla[1] + 1))):
                    _random_child(db, rng, t, today)
            t.use_mahalla(0)

        _demo_patients(db, rng, tenants["PL-NUK-001"], today)
        from app.services.visit_intensity import confirm_light_visit_plan, pregnancy_visit_plan

        for t in tenants.values():
            confirmed_n = 0
            active_green = db.query(Pregnancy).join(Patient).filter(
                Patient.polyclinic_id == t.polyclinic.id,
                Pregnancy.status == "active",
                Pregnancy.current_zone == "green",
            ).all()
            for pr in active_green:
                pl = pregnancy_visit_plan(db, pr, log_recommendation=True)
                if pl["eligible"] and not pr.patient.code.endswith("DEMO3") and confirmed_n < 2:
                    confirm_light_visit_plan(db, pr, t.users["doctor"])
                    confirmed_n += 1
        db.commit()
        stats = {
            "polyclinics": db.query(Polyclinic).count(), "mahallas": db.query(Mahalla).count(),
            "patients": db.query(Patient).count(), "pregnancies": db.query(Pregnancy).count(),
            "visits": db.query(Visit).count(), "assessments": db.query(RiskAssessment).count(),
            "alerts": db.query(Alert).count(), "newborns": db.query(Newborn).count(), "users": db.query(User).count(),
            "audit": db.query(AuditLog).count(),
            "patients_per_polyclinic": {t.pdef["code"]: db.query(Patient).filter_by(polyclinic_id=t.polyclinic.id).count()
                                        for t in tenants.values()},
        }
        zones = {z: db.query(Pregnancy).filter_by(status="active", current_zone=z).count() for z in ("red", "yellow", "green")}
        stats["zones_per_polyclinic"] = {
            t.pdef["code"]: {z: db.query(Pregnancy).join(Patient).filter(
                Pregnancy.status == "active", Pregnancy.current_zone == z, Patient.polyclinic_id == t.polyclinic.id).count()
                for z in ("green", "yellow", "red")} for t in tenants.values()}
        stats["child_zones"] = {z: db.query(Newborn).filter_by(status="active", current_zone=z).count()
                                for z in ("red", "yellow", "green")}
    stats["active_zones"] = zones
    stats["seconds"] = round(time.time() - t0, 1)
    return stats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    from app.risk.ml import load_model

    if load_model() is None:
        print("WARNING: ML model artifact not found - seeding with rules + trends only. Run ml/train.py first.")
    print(seed(a.seed))


if __name__ == "__main__":
    main()
