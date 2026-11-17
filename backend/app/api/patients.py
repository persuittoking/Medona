from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import audit
from app.api.tenancy import Tenant, staff
from app.db import get_db
from app.models import Alert, Patient, Pregnancy, RiskAssessment, User, Visit
from app.services.geo import decrypt_home
from app.risk import thresholds as T
from app.risk.features import bmi, gest_weeks
from app.schemas import PatientDetail, PatientRow, PiiOut
from app.security.crypto import decrypt, mask_name, mask_phone, mask_pinfl
from app.services.alerts import alert_out
from app.services.scoring import preg_dict

router = APIRouter(prefix="/api/patients", tags=["patients"])

HISTORY_UZ = {
    "previous_cs": "Oldingi kesarcha kesish", "hist_stillbirth": "O'lik tug'ilish", "hist_preterm": "Muddatidan oldin tug'ruq",
    "hist_preeclampsia": "Preeklampsiya", "hist_pph": "Tug'ruqdan keyingi qon ketish", "diabetes": "Qandli diabet",
    "chronic_htn": "Surunkali gipertenziya", "heart": "Yurak kasalligi", "kidney": "Buyrak kasalligi",
    "thyroid": "Qalqonsimon bez kasalligi", "epilepsy": "Epilepsiya", "multiple_pregnancy": "Ko'p homilali",
    "rh_negative": "Rezus-manfiy",
}


def _age(birth: date, on: date | None = None) -> int:
    on = on or date.today()
    return on.year - birth.year - ((on.month, on.day) < (birth.month, birth.day))


def _is_overdue(gw: float, last: date | None) -> bool:
    if last is None:
        return True
    limit = T.OVERDUE_DAYS_3RD_TRIMESTER if gw >= T.THIRD_TRIMESTER_WEEKS else T.OVERDUE_DAYS_OTHER
    return (date.today() - last).days > limit


def risk_out(ra: RiskAssessment | None) -> dict | None:
    if ra is None:
        return None
    return {"id": ra.id, "zone": ra.zone, "ml_probability": ra.ml_probability, "rule_hits": ra.rule_hits,
            "trend_hits": ra.trend_hits, "notes": ra.notes or [], "shap_top": ra.shap_top,
            "model_version": ra.model_version, "explanation_uz": ra.explanation_uz, "created_at": ra.created_at}


@router.get("", response_model=list[PatientRow])
def list_patients(zone: str | None = None, mahalla_id: int | None = None, trimester: int | None = Query(None, ge=1, le=3),
                  overdue: bool | None = None, q: str | None = None, status: str = "active",
                  t: Tenant = Depends(staff())) -> list[dict]:
    db = t.db
    last_visit = select(Visit.pregnancy_id, func.max(Visit.visit_date).label("last")).group_by(Visit.pregnancy_id).subquery()
    stmt = (select(Patient, Pregnancy, last_visit.c.last).join(Pregnancy, Pregnancy.patient_id == Patient.id)
            .outerjoin(last_visit, last_visit.c.pregnancy_id == Pregnancy.id)
            .where(Pregnancy.status == status).options(selectinload(Patient.mahalla), selectinload(Patient.polyclinic)))
    stmt = t.patients(stmt)
    if zone:
        stmt = stmt.where(Pregnancy.current_zone == zone)
    if mahalla_id:
        stmt = stmt.where(Patient.mahalla_id == mahalla_id)
    if q:
        stmt = stmt.where(Patient.code.ilike(f"%{q.strip()}%"))
    rows = []
    today = date.today()
    for pat, preg, last in db.execute(stmt).all():
        gw = gest_weeks(preg.lmp_date, today)
        tri = 1 if gw < 14 else (2 if gw < 28 else 3)
        od = preg.status == "active" and _is_overdue(gw, last)
        if (trimester and tri != trimester) or (overdue is not None and od != overdue):
            continue
        rows.append({"patient_id": pat.id, "pregnancy_id": preg.id, "code": pat.code,
                     "name_masked": mask_name(decrypt(pat.full_name_enc)), "age": _age(pat.birth_date),
                     "gestational_weeks": gw, "trimester": tri, "zone": preg.current_zone,
                     "risk": preg.current_risk_score, "last_visit_date": last, "overdue": od,
                     "district_name": pat.polyclinic.district.name, "mahalla": pat.mahalla.name})
    order = {"red": 0, "yellow": 1, "green": 2}
    rows.sort(key=lambda r: (order[r["zone"]], -(r["risk"] or 0)))
    return rows


@router.get("/{patient_id}", response_model=PatientDetail)
def patient_detail(patient_id: int, request: Request, t: Tenant = Depends(staff())) -> dict:
    db, user = t.db, t.user
    pat = t.get_patient(patient_id)
    preg = sorted(pat.pregnancies, key=lambda p: (p.status != "active", -p.id))[0]
    audit(db, user, "view_patient", "patient", pat.id, request)
    db.commit()
    assessments = db.scalars(select(RiskAssessment).where(RiskAssessment.pregnancy_id == preg.id)
                             .order_by(RiskAssessment.id)).all()
    alerts = db.scalars(select(Alert).where(Alert.pregnancy_id == preg.id).order_by(Alert.id.desc())).all()
    newborns = []
    for nb in preg.newborns:
        ra = db.scalars(select(RiskAssessment).where(RiskAssessment.newborn_id == nb.id)
                        .order_by(RiskAssessment.id.desc())).first()
        newborns.append({"id": nb.id, "birth_date": nb.birth_date, "gestational_weeks_at_birth": nb.gestational_weeks_at_birth,
                         "birth_weight_g": nb.birth_weight_g, "apgar_5": nb.apgar_5, "zone": nb.current_zone,
                         "hits": ra.rule_hits if ra else []})
    nurse = db.get(User, pat.assigned_nurse_id) if pat.assigned_nurse_id else None
    b = bmi(preg_dict(preg))
    return {
        "patient_id": pat.id, "code": pat.code, "name_masked": mask_name(decrypt(pat.full_name_enc)),
        "pinfl_masked": mask_pinfl(decrypt(pat.pinfl_enc)), "phone_masked": mask_phone(decrypt(pat.phone_enc)),
        "age": _age(pat.birth_date), "district_name": pat.polyclinic.district.name,
        "region_name": pat.polyclinic.district.region.name, "polyclinic_name": pat.polyclinic.name,
        "mahalla": pat.mahalla.name, "mahalla_id": pat.mahalla_id,
        "home": dict(zip(("lat", "lon"), decrypt_home(pat.home_enc))),
        "distance_to_perinatal_km": pat.distance_to_perinatal_km,
        "nurse": nurse.full_name if nurse else None,
        "pregnancy": {
            "id": preg.id, "status": preg.status, "lmp_date": preg.lmp_date, "booking_date": preg.booking_date,
            "gestational_weeks": gest_weeks(preg.lmp_date, date.today()), "edd": preg.lmp_date + timedelta(days=280),
            "gravidity": preg.gravidity, "parity": preg.parity,
            "history": [txt for k, txt in HISTORY_UZ.items() if getattr(preg, k)]
            + ([f"{preg.miscarriages_count} marta homila tushishi"] if preg.miscarriages_count else []),
            "current_zone": preg.current_zone, "current_risk_score": preg.current_risk_score,
            "bmi_booking": None if b != b else b, "height_cm": preg.height_cm, "booking_weight_kg": preg.booking_weight_kg,
        },
        "latest_assessment": risk_out(assessments[-1] if assessments else None),
        "visits": preg.visits,
        "assessments": [risk_out(a) for a in assessments],
        "alerts": [alert_out(a, db) for a in alerts],
        "newborns": newborns,
    }


@router.post("/{patient_id}/reveal", response_model=PiiOut)
def reveal_pii(patient_id: int, request: Request, t: Tenant = Depends(staff())) -> dict:
    """Show full name / PINFL / phone. Every call is written to the audit log."""
    db, user = t.db, t.user
    pat = t.get_patient(patient_id)
    audit(db, user, "reveal_pii", "patient", pat.id, request)
    db.commit()
    return {"full_name": decrypt(pat.full_name_enc), "pinfl": decrypt(pat.pinfl_enc), "phone": decrypt(pat.phone_enc)}
