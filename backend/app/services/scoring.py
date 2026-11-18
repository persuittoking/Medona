"""Glue between ORM rows and the (pure) risk engine."""
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alert, Pregnancy, RiskAssessment, Visit, utcnow
from app.risk.engine import score_pregnancy
from app.risk.features import gest_weeks
from app.risk.rules import ZONE_ORDER
from app.services.alerts import first_assignee, record_event, sla_delta

PREG_FIELDS = [
    "lmp_date", "booking_date", "gravidity", "parity", "previous_cs", "hist_stillbirth", "hist_preterm",
    "miscarriages_count", "hist_preeclampsia", "hist_pph", "diabetes", "chronic_htn", "heart", "kidney",
    "thyroid", "epilepsy", "multiple_pregnancy", "rh_negative", "interpregnancy_months", "height_cm",
    "booking_weight_kg",
]
VISIT_FIELDS = [
    "visit_date", "gestational_weeks", "systolic", "diastolic", "proteinuria", "hemoglobin_g_l",
    "fasting_glucose_mmol", "weight_kg", "temperature_c", "fetal_heart_rate", "fundal_height_cm", "symptoms",
]


def preg_dict(preg: Pregnancy) -> dict:
    d = {k: getattr(preg, k) for k in PREG_FIELDS}
    d["birth_date"] = preg.patient.birth_date
    d["distance_to_perinatal_km"] = preg.patient.distance_to_perinatal_km
    return d


def visit_dict(v: Visit | dict) -> dict:
    if isinstance(v, dict):
        return {k: v.get(k) for k in VISIT_FIELDS}
    return {k: getattr(v, k) for k in VISIT_FIELDS}


def risk_out(ra: RiskAssessment | None) -> dict | None:
    if ra is None:
        return None
    return {"id": ra.id, "zone": ra.zone, "ml_probability": ra.ml_probability, "rule_hits": ra.rule_hits,
            "trend_hits": ra.trend_hits, "notes": ra.notes or [], "shap_top": ra.shap_top,
            "model_version": ra.model_version, "explanation_uz": ra.explanation_uz, "created_at": ra.created_at}


def latest_assessment(db: Session, pregnancy_id: int) -> RiskAssessment | None:
    return db.scalars(select(RiskAssessment).where(RiskAssessment.pregnancy_id == pregnancy_id)
                      .order_by(RiskAssessment.id.desc()).limit(1)).first()


def recent_ml_probs(db: Session, pregnancy_id: int, n: int = 2) -> list[float | None]:
    """ML probabilities of the last `n` assessments, oldest first (for the P05 / T05 trend rules)."""
    rows = db.scalars(select(RiskAssessment.ml_probability).where(RiskAssessment.pregnancy_id == pregnancy_id)
                      .order_by(RiskAssessment.id.desc()).limit(n)).all()
    return list(reversed(rows))


def score_new_visit(db: Session, preg: Pregnancy, new_visit: dict) -> dict:
    """Score a (not yet saved) visit on top of the stored history. No DB writes."""
    new_visit = dict(new_visit)
    new_visit.setdefault("visit_date", date.today())
    if new_visit.get("gestational_weeks") is None:
        new_visit["gestational_weeks"] = gest_weeks(preg.lmp_date, new_visit["visit_date"])
    history = [visit_dict(v) for v in preg.visits if v.visit_date <= new_visit["visit_date"]]
    probs = recent_ml_probs(db, preg.id)
    return score_pregnancy(preg_dict(preg), history + [visit_dict(new_visit)],
                           prev_ml_prob=probs[-1] if probs else None, prev_ml_probs=probs or None)


def store_assessment(db: Session, preg: Pregnancy, visit: Visit, result: dict,
                     created_at: datetime | None = None) -> RiskAssessment:
    ra = RiskAssessment(
        pregnancy_id=preg.id, visit_id=visit.id, zone=result["zone"], rule_hits=result["rule_hits"],
        trend_hits=result["trend_hits"], notes=result["notes"], ml_probability=result["ml_probability"],
        shap_top=result["shap_top"], model_version=result["model_version"],
        explanation_uz=result["explanation_uz"], created_at=created_at or utcnow(),
    )
    db.add(ra)
    db.flush()
    return ra


def create_alert_if_worse(db: Session, preg: Pregnancy, old_zone: str, ra: RiskAssessment,
                          now: datetime | None = None) -> Alert | None:
    """An alert is created only when the zone gets WORSE (green->yellow, *->red)."""
    if ZONE_ORDER[ra.zone] <= ZONE_ORDER[old_zone]:
        return None
    now = now or utcnow()
    poly = preg.patient.polyclinic
    first = first_assignee(db, poly.id, poly.district_id, ra.zone)
    alert = Alert(risk_assessment_id=ra.id, pregnancy_id=preg.id, level=ra.zone, status="open",
                  assigned_user_id=first.id if first else None, sla_due_at=now + sla_delta(ra.zone), created_at=now)
    db.add(alert)
    db.flush()
    record_event(db, alert, "created", assignee_id=alert.assigned_user_id, at=now)
    return alert


def apply_assessment(preg: Pregnancy, ra: RiskAssessment) -> None:
    preg.current_zone = ra.zone
    preg.current_risk_score = ra.ml_probability
