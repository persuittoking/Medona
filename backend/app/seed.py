"""Reset and seed the database with SYNTHETIC demo data (multi-tenant by polyclinic).

Hierarchy: Region -> District -> Polyclinic (tenant) -> Mahalla -> Patients (home point inside the mahalla polygon).
Each mahalla gets 50-60 active pregnancies + a few recent deliveries. Candidates are scored by the real risk
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
from app.risk.engine import score_pregnancy
from app.risk.newborn import newborn_hits, newborn_zone
from app.security.auth import hash_password
from app.security.crypto import encrypt
from app.services.geo import encrypt_home, sample_points, validate_home
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
NEWBORNS_PER_MAHALLA = (2, 4)    # recently delivered (mother + newborn), inclusive range
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
    """Seed-time context of one polyclinic: its mahalla, staff and a pool of home points inside the polygon."""

    def __init__(self, db, rng, pdef: dict, rdef: dict, ddef: dict, district: District, pw: str):
        self.pdef, self.rdef, self.ddef, self.district = pdef, rdef, ddef, district
        feat = load_boundary(pdef["mahalla_key"])
        poly = as_shape(feat)
        self.polyclinic = Polyclinic(code=pdef["code"], name=pdef["name"], district_id=district.id,
                                     address=pdef["address"], lat=round(poly.centroid.y, 6), lon=round(poly.centroid.x, 6))
        db.add(self.polyclinic)
        db.flush()
        props = feat["properties"]
        self.mahalla = Mahalla(name=props["name"], polyclinic_id=self.polyclinic.id, boundary_geojson=feat["geometry"],
                               boundary_source=props["source"], demo_boundary=bool(props.get("demo_boundary", True)),
                               centroid_lat=round(poly.centroid.y, 6), centroid_lon=round(poly.centroid.x, 6))
        db.add(self.mahalla)
        self.users: dict[str, User] = {}
        for role, title in [("nurse", "Patronaj hamshirasi"), ("doctor", "Oilaviy shifokor"),
                            ("specialist", "OvaBMU mutaxassisi")]:
            u = User(username=role, full_name=f"{title} ({pdef['code']})", role=role, polyclinic_id=self.polyclinic.id,
                     district_id=district.id, region_id=district.region_id, password_hash=pw)
            db.add(u)
            self.users[role] = u
        db.flush()
        self._homes = sample_points(feat["geometry"], 500, rng)
        self._home_i = 0
        self._seq = 400

    def next_code(self) -> int:
        self._seq += 1
        return self._seq

    def next_home_distance_km(self) -> float:
        """Distance to the perinatal centre of the home point the next add_patient() will use."""
        lat, lon = self._homes[self._home_i]
        per = self.rdef["perinatal"]
        return round(haversine_km(lat, lon, per["lat"], per["lon"]), 1)

    def add_patient(self, db, p: dict) -> Patient:
        lat, lon = self._homes[self._home_i]
        self._home_i += 1
        validate_home(self.mahalla.boundary_geojson, lat, lon)
        per = self.rdef["perinatal"]
        pat = Patient(code=p["code"], full_name_enc=encrypt(p["full_name"]), pinfl_enc=encrypt(p["pinfl"]),
                      phone_enc=encrypt(p["phone"]), home_enc=encrypt_home(lat, lon), birth_date=p["birth_date"],
                      polyclinic_id=self.polyclinic.id, mahalla_id=self.mahalla.id,
                      distance_to_perinatal_km=round(haversine_km(lat, lon, per["lat"], per["lon"]), 1),
                      assigned_nurse_id=self.users["nurse"].id)
        db.add(pat)
        db.flush()
        return pat


def _add_pregnancy(db, pat: Patient, preg: dict, status: str = "active") -> Pregnancy:
    pr = Pregnancy(patient_id=pat.id, status=status, **{k: preg[k] for k in PREG_KEYS})
    db.add(pr)
    db.flush()
    db.refresh(pr)
    return pr


def _score_history(db, rng, pr: Pregnancy, visits: list[dict], nurse: User | None, today: date) -> None:
    """Insert visits chronologically, scoring each one as if entered on that day."""
    zone, prev_prob, hist = "green", None, []
    for v in visits:
        row = Visit(pregnancy_id=pr.id, entered_by=nurse.id if nurse else None, notes=v.get("notes"),
                    **visit_dict(v))
        db.add(row)
        db.flush()
        hist.append(visit_dict(v))
        res = score_pregnancy(preg_dict(pr), hist, prev_ml_prob=prev_prob)
        at = datetime.combine(v["visit_date"], datetime.min.time()) + timedelta(hours=5, minutes=int(rng.integers(0, 300)))
        at = min(at, utcnow() - timedelta(minutes=5))  # never in the future
        ra = store_assessment(db, pr, row, res, created_at=at)
        alert = create_alert_if_worse(db, pr, zone, ra, now=at)
        if alert is not None and (today - v["visit_date"]).days > 2:
            alert.acknowledged_at = at + timedelta(minutes=int(rng.integers(15, 240)))
            alert.status = "resolved"
            alert.resolved_at = alert.acknowledged_at
            alert.action_taken = str(rng.choice(ACTIONS))
        elif alert is not None and rng.random() < 0.5:
            alert.acknowledged_at = at + timedelta(minutes=int(rng.integers(10, 90)))
            alert.status = "acknowledged"
            alert.action_taken = str(rng.choice(ACTIONS))
        zone, prev_prob = ra.zone, ra.ml_probability
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

    # DEMO1 — "Dilnoza", 19 y, first pregnancy, 31 weeks: BP slowly rising (118/76 -> 128/82 -> 136/88),
    # Hb falling (118 -> 104), fundal height slightly behind (2.3 cm, below the T04 rule) -> no single rule
    # fires, the ML model raises the zone to YELLOW ("zona model tomonidan oshirildi").
    # Live demo: new visit BP 152/98, proteinuria +2, severe headache -> RED (R02).
    _, p1, lmp = base("QQR-NUK-DEMO1", "Dilnoza Karimova", 19, 31.3)
    _score_history(db, rng, p1, [
        v(lmp, 10.0, 112, 72, 121, 58.0),
        v(lmp, 16.3, 114, 74, 120, 59.8),
        v(lmp, 22.3, 118, 76, 118, 62.0),
        v(lmp, 26.3, 128, 82, 112, 64.0),
        v(lmp, 29.3, 136, 88, 104, 65.6, fundal=27.0, syms=["edema"]),
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

    # DEMO3 — healthy pregnancy -> GREEN (the system does not over-alarm).
    _, p3, lmp = base("QQR-NUK-DEMO3", "Madina Yusupova", 26, 24.0, gravidity=2, parity=1,
                      interpregnancy_months=38, booking_weight_kg=57.0)
    _score_history(db, rng, p3, [
        v(lmp, 9.0, 110, 70, 128, 57.0),
        v(lmp, 16.5, 112, 70, 126, 59.0),
        v(lmp, 22.5, 110, 72, 124, 61.6),
    ], nurse, today)

    # DEMO4 — delivered: newborn with low birth weight + fast breathing -> newborn RED.
    _, p4, lmp = base("QQR-NUK-DEMO4", "Shahnoza Ergasheva", 23, 39.5)
    p4.status, p4.current_zone = "delivered", "yellow"
    _score_history(db, rng, p4, [v(lmp, 11.0, 112, 70, 116, 58.0), v(lmp, 30.0, 120, 78, 108, 66.0)], nurse, today)
    _add_newborn(db, p4, today - timedelta(days=4), 36.0, 2150, 8,
                 {"check_date": today - timedelta(days=1), "resp_rate": 64, "temperature_c": 36.9, "weight_g": 2080})


def _add_newborn(db, pr: Pregnancy, birth: date, ga: float, bw: int, apgar: int, check: dict | None) -> Newborn:
    nb = Newborn(pregnancy_id=pr.id, birth_date=birth, gestational_weeks_at_birth=ga, birth_weight_g=bw, apgar_5=apgar)
    db.add(nb)
    db.flush()
    ck = None
    if check:
        ck = NewbornCheck(newborn_id=nb.id, **check)
        db.add(ck)
        db.flush()
    mother_red = any(a.zone == "red" for a in db.query(RiskAssessment).filter_by(pregnancy_id=pr.id))
    nb_dict = {"birth_weight_g": bw, "gestational_weeks_at_birth": ga, "apgar_5": apgar, "birth_date": birth}
    ck_dict = {k: getattr(ck, k) for k in ("not_feeding_well", "convulsions", "resp_rate", "severe_chest_indrawing",
                                           "temperature_c", "movement_only_when_stimulated", "jaundice_first_24h",
                                           "jaundice_palms_soles")} if ck else None
    hits = newborn_hits(nb_dict, ck_dict, mother_red_3rd_trimester=mother_red, today=date.today())
    nb.current_zone = newborn_zone(hits)
    db.add(RiskAssessment(newborn_id=nb.id, check_id=ck.id if ck else None, zone=nb.current_zone, rule_hits=hits,
                          trend_hits=[], notes=[], shap_top=[],
                          explanation_uz="Chaqaloq: " + ("; ".join(h["uz_text"] for h in hits) or "xavf belgilari yo'q")))
    return nb


def _final_zone(preg: dict, visits: list[dict]) -> str:
    """Zone after the last visit, scored visit by visit exactly as _score_history does (pure, no DB)."""
    prev_prob, res = None, None
    for k in range(len(visits)):
        res = score_pregnancy(preg, [visit_dict(v) for v in visits[: k + 1]], prev_ml_prob=prev_prob)
        prev_prob = res["ml_probability"]
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
    if delivered:
        ga = round(min(cur_w, 41.0), 1)
        bw = int(np.clip(rng.normal(3300 - max(0, 39 - ga) * 220, 420), 1200, 4800))
        ck = {"check_date": today - timedelta(days=int(rng.integers(0, 3))), "resp_rate": int(rng.integers(36, 58)),
              "temperature_c": round(float(rng.normal(36.8, 0.25)), 1), "weight_g": bw - 80,
              "jaundice_palms_soles": bool(rng.random() < 0.04), "not_feeding_well": bool(rng.random() < 0.04)}
        _add_newborn(db, pr, today - timedelta(days=int(rng.integers(1, 20))), ga, bw,
                     int(rng.integers(6, 10)), ck if rng.random() < 0.85 else None)


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


def seed(seed_value: int = 7, active_per_mahalla: tuple[int, int] = ACTIVE_PER_MAHALLA) -> dict:
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
            if rdef["code"] == "QQR":
                db.add(User(username="region.admin", full_name=f"{rdef['name']} sog'liqni saqlash vazirligi",
                            role="region_admin", region_id=region.id, password_hash=pw))
        db.flush()

        for t in tenants.values():
            quotas = zone_quotas(rng, int(rng.integers(active_per_mahalla[0], active_per_mahalla[1] + 1)))
            if t.pdef["code"] == "PL-NUK-001":
                for z, k in DEMO_ACTIVE_ZONES.items():  # DEMO1-3 are added below and count towards the mix
                    quotas[z] -= k
            _fill_register(db, rng, t, today, quotas)
            for _ in range(int(rng.integers(NEWBORNS_PER_MAHALLA[0], NEWBORNS_PER_MAHALLA[1] + 1))):
                _insert_pregnancy(db, rng, t, today, _draw_candidate(rng, t, today, delivered=True), delivered=True)

        _demo_patients(db, rng, tenants["PL-NUK-001"], today)
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
