"""Glue between child ORM rows (Newborn / NewbornCheck) and the pure infant risk engine (app/risk/infant.py)."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Newborn, NewbornCheck, Pregnancy, RiskAssessment, Visit, utcnow
from app.risk import thresholds as T
from app.risk.infant import age_days, given_vaccines, overdue_vaccines, score_infant, severity_score

CHECK_FIELDS = [
    "check_date", "not_feeding_well", "convulsions", "resp_rate", "severe_chest_indrawing", "temperature_c",
    "movement_only_when_stimulated", "jaundice_first_24h", "jaundice_palms_soles", "weight_g", "length_cm",
    "head_circ_cm", "feeding", "vomiting_everything", "diarrhoea_days", "blood_in_stool", "cough_days", "lethargic",
    "vaccines_given",
]
CHILD_FIELDS = ["birth_date", "sex", "birth_weight_g", "gestational_weeks_at_birth", "apgar_5"]


def child_dict(nb: Newborn) -> dict:
    return {k: getattr(nb, k) for k in CHILD_FIELDS}


def check_dict(ck: NewbornCheck | dict) -> dict:
    get = ck.get if isinstance(ck, dict) else (lambda k: getattr(ck, k))
    d = {k: get(k) for k in CHECK_FIELDS}
    d["vaccines_given"] = list(d["vaccines_given"] or [])
    return d


def child_code(preg: Pregnancy, n: int) -> str:
    return f"B-{preg.patient.code}-{n}"


def make_child(db: Session, preg: Pregnancy, *, birth_date: date, ga: float, birth_weight_g: int,
               apgar_5: int | None, sex: str) -> Newborn:
    """Register a child of this pregnancy. Tenant keys come from the MOTHER's patient record."""
    pat = preg.patient
    n = 1 + len(db.scalars(select(Newborn.id).join(Pregnancy).where(Pregnancy.patient_id == pat.id)).all())
    nb = Newborn(pregnancy_id=preg.id, code=child_code(preg, n), sex=sex, status="active",
                 polyclinic_id=pat.polyclinic_id, mahalla_id=pat.mahalla_id, birth_date=birth_date,
                 gestational_weeks_at_birth=ga, birth_weight_g=birth_weight_g, apgar_5=apgar_5)
    db.add(nb)
    db.flush()
    return nb


def mother_red_3rd_trimester(db: Session, preg_id: int) -> bool:
    """N12: the mother was RED at a visit from 28 weeks."""
    row = db.scalars(select(RiskAssessment.id).join(Visit, RiskAssessment.visit_id == Visit.id)
                     .where(RiskAssessment.pregnancy_id == preg_id, RiskAssessment.zone == "red",
                            Visit.gestational_weeks >= T.THIRD_TRIMESTER_WEEKS).limit(1)).first()
    return row is not None


def score_child(db: Session, nb: Newborn, new_check: dict | None = None, today: date | None = None) -> dict:
    """Score the stored history (+ an optional unsaved check). No DB writes."""
    history = [check_dict(c) for c in nb.checks]
    if new_check is not None:
        new_check = dict(new_check)
        new_check.setdefault("check_date", date.today())
        history = [c for c in history if c["check_date"] <= new_check["check_date"]] + [check_dict(new_check)]
    on = today or (history[-1]["check_date"] if history else date.today())
    return score_infant(child_dict(nb), history, today=on,
                        mother_red_3rd_trimester=mother_red_3rd_trimester(db, nb.pregnancy_id))


def check_extras(nb: Newborn, check: dict, prior: list[NewbornCheck]) -> dict:
    """Computed columns of a check: age in days and the overdue vaccine codes on that day."""
    given = given_vaccines([check_dict(c) for c in prior] + [check_dict(check)])
    return {"age_days": age_days(nb.birth_date, check["check_date"]),
            "vaccines_due_overdue": overdue_vaccines(nb.birth_date, given, check["check_date"])}


def store_child_assessment(db: Session, nb: Newborn, ck: NewbornCheck | None, result: dict,
                           created_at: datetime | None = None) -> RiskAssessment:
    ra = RiskAssessment(newborn_id=nb.id, check_id=ck.id if ck else None, zone=result["zone"],
                        rule_hits=result["rule_hits"], trend_hits=result["trend_hits"], notes=result["notes"],
                        ml_probability=None, shap_top=[], model_version=None, explanation_uz=result["explanation_uz"],
                        created_at=created_at or utcnow())
    db.add(ra)
    db.flush()
    return ra


def apply_child_assessment(nb: Newborn, ra: RiskAssessment) -> None:
    nb.current_zone = ra.zone
    nb.current_risk_score = severity_score({"zone": ra.zone, "rule_hits": ra.rule_hits, "trend_hits": ra.trend_hits})


def latest_child_assessment(db: Session, newborn_id: int) -> RiskAssessment | None:
    return db.scalars(select(RiskAssessment).where(RiskAssessment.newborn_id == newborn_id)
                      .order_by(RiskAssessment.id.desc()).limit(1)).first()


def refresh_status(nb: Newborn, today: date | None = None) -> None:
    """active -> graduated after the 1st birthday (deceased / moved are set by staff and never changed here)."""
    if nb.status == "active" and age_days(nb.birth_date, today or date.today()) > T.INFANT_MAX_DAYS:
        nb.status = "graduated"
