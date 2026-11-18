"""Children 0-12 months ("Bolalar"): list, card, infant check with live risk preview. Tenant-scoped via Tenant."""
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import func, select, update

from app.api.deps import audit
from app.api.tenancy import Tenant, staff
from app.models import Alert, Newborn, NewbornCheck, RiskAssessment
from app.risk import thresholds as T
from app.risk.infant import age_days, age_months, vaccine_status, wfa_z
from app.schemas import ChildCheckCreatedOut, ChildCheckIn, ChildDetail, ChildRow, RiskOut
from app.services.ai_summary import generate_cached
from app.services.alerts import alert_out
from app.services.children import (
    apply_child_assessment,
    check_dict,
    check_extras,
    refresh_status,
    score_child,
    store_child_assessment,
)
from app.services.closed_loop import after_assessment
from app.services.notify import notify_new_alert_job
from app.services.scoring import create_alert_if_worse, risk_out

router = APIRouter(prefix="/api/children", tags=["children"])
ZONE_ORDER = {"red": 0, "yellow": 1, "green": 2}


def graduate_due(t: Tenant, today: date | None = None) -> None:
    """Children past their 1st birthday leave the active register (status "graduated")."""
    today = today or date.today()
    cutoff = date.fromordinal(today.toordinal() - T.INFANT_MAX_DAYS)
    res = t.db.execute(update(Newborn).where(Newborn.polyclinic_id == t.polyclinic_id, Newborn.status == "active",
                                             Newborn.birth_date < cutoff).values(status="graduated"))
    if res.rowcount:
        t.db.commit()


def is_overdue(nb: Newborn, last: date | None, today: date) -> bool:
    days = age_days(nb.birth_date, today)
    if days <= T.NEONATAL_DAYS:
        return last is None and days > T.NB_CHECK_BY_DAY
    return (today - (last or nb.birth_date)).days > T.INF_CHECK_INTERVAL_DAYS


def main_reason(ra: RiskAssessment | None) -> str | None:
    hits = (ra.rule_hits + ra.trend_hits) if ra else []
    red = [h for h in hits if h["zone"] == "red"]
    return (red or hits)[0]["uz_text"] if hits else None


def latest_by_child(t: Tenant, ids: list[int]) -> dict[int, RiskAssessment]:
    if not ids:
        return {}
    last = (select(RiskAssessment.newborn_id, func.max(RiskAssessment.id).label("rid"))
            .where(RiskAssessment.newborn_id.in_(ids)).group_by(RiskAssessment.newborn_id).subquery())
    rows = t.db.scalars(select(RiskAssessment).join(last, RiskAssessment.id == last.c.rid)).all()
    return {ra.newborn_id: ra for ra in rows}


def child_rows(t: Tenant, status: str = "active", zone: str | None = None, q: str | None = None,
               mahalla_id: int | None = None, all_mahallas: bool = False) -> list[dict]:
    graduate_due(t)
    last_check = (select(NewbornCheck.newborn_id, func.max(NewbornCheck.check_date).label("last"))
                  .group_by(NewbornCheck.newborn_id).subquery())
    stmt = t.children(select(Newborn, last_check.c.last).outerjoin(last_check, last_check.c.newborn_id == Newborn.id)
                      .where(Newborn.status == status))
    if zone:
        stmt = stmt.where(Newborn.current_zone == zone)
    if mahalla_id:
        stmt = stmt.where(Newborn.mahalla_id == mahalla_id)
    elif not all_mahallas and t.user.role == "nurse" and t.user.mahalla_id is not None:
        stmt = stmt.where(Newborn.mahalla_id == t.user.mahalla_id)
    if q:
        stmt = stmt.where(Newborn.code.ilike(f"%{q.strip()}%"))
    rows = t.db.execute(stmt).all()
    ras = latest_by_child(t, [nb.id for nb, _ in rows])
    today = date.today()
    out = []
    for nb, last in rows:
        mother = nb.pregnancy.patient
        out.append({"newborn_id": nb.id, "code": nb.code, "mother_patient_id": mother.id, "mother_code": mother.code,
                    "sex": nb.sex, "age_days": age_days(nb.birth_date, today), "zone": nb.current_zone,
                    "risk": nb.current_risk_score, "last_check_date": last, "overdue": is_overdue(nb, last, today),
                    "mahalla": mother.mahalla.name, "mahalla_id": mother.mahalla_id,
                    "main_reason": main_reason(ras.get(nb.id))})
    out.sort(key=lambda r: (ZONE_ORDER[r["zone"]], -(r["risk"] or 0), r["age_days"]))
    return out


@router.get("", response_model=list[ChildRow])
def list_children(zone: str | None = None, q: str | None = None, status: str = "active",
                  mahalla_id: int | None = None, all_mahallas: bool = False,
                  t: Tenant = Depends(staff())) -> list[dict]:
    return child_rows(t, status, zone, q, mahalla_id=mahalla_id, all_mahallas=all_mahallas)


def _growth(nb: Newborn) -> tuple[list[dict], list[dict]]:
    pts = [{"age_months": age_months(nb.birth_date, c.check_date), "weight_kg": c.weight_g / 1000,
            "z": wfa_z(nb.sex, age_days(nb.birth_date, c.check_date), c.weight_g / 1000) if nb.sex else None}
           for c in nb.checks if c.weight_g]
    pts.insert(0, {"age_months": 0.0, "weight_kg": nb.birth_weight_g / 1000,
                   "z": wfa_z(nb.sex, 0, nb.birth_weight_g / 1000) if nb.sex else None})
    table = T.WFA_TABLE["f" if nb.sex == "f" else "m"]
    ref = [{"age_months": float(m), "median": med, "minus2sd": low} for m, (med, low) in enumerate(table)]
    return pts, ref


@router.get("/{newborn_id}", response_model=ChildDetail)
def child_detail(newborn_id: int, request: Request, t: Tenant = Depends(staff())) -> dict:
    db = t.db
    nb = t.get_newborn(newborn_id)
    audit(db, t.user, "view_child", "newborn", nb.id, request)
    db.commit()
    mother = nb.pregnancy.patient
    assessments = db.scalars(select(RiskAssessment).where(RiskAssessment.newborn_id == nb.id)
                             .order_by(RiskAssessment.id)).all()
    alerts = db.scalars(select(Alert).where(Alert.newborn_id == nb.id).order_by(Alert.id.desc())).all()
    growth, ref = _growth(nb)
    given = {c for ck in nb.checks for c in (ck.vaccines_given or [])}
    return {
        "newborn_id": nb.id, "code": nb.code, "sex": nb.sex, "status": nb.status, "birth_date": nb.birth_date,
        "age_days": age_days(nb.birth_date, date.today()), "gestational_weeks_at_birth": nb.gestational_weeks_at_birth,
        "birth_weight_g": nb.birth_weight_g, "apgar_5": nb.apgar_5, "zone": nb.current_zone,
        "mother_patient_id": mother.id, "mother_code": mother.code, "mahalla": mother.mahalla.name,
        "polyclinic_name": mother.polyclinic.name,
        "latest_assessment": risk_out(assessments[-1] if assessments else None),
        "checks": nb.checks, "assessments": [risk_out(a) for a in assessments],
        "alerts": [alert_out(a, db) for a in alerts], "growth": growth, "reference": ref,
        "vaccines": vaccine_status(nb.birth_date, given, date.today()),
    }


def _check_payload(body: ChildCheckIn, nb: Newborn) -> dict:
    d = body.model_dump(exclude={"newborn_id"})
    d["check_date"] = d["check_date"] or date.today()
    if d["check_date"] > date.today():
        raise HTTPException(422, "Ko'rik sanasi kelajakda bo'lishi mumkin emas")
    if d["check_date"] < nb.birth_date:
        raise HTTPException(422, "Ko'rik sanasi tug'ilgan sanadan oldin bo'lishi mumkin emas")
    return d


@router.post("/risk/preview", response_model=RiskOut)
def child_risk_preview(body: ChildCheckIn, t: Tenant = Depends(staff())) -> dict:
    """Score an infant check WITHOUT saving anything (live preview while the nurse types)."""
    nb = t.get_newborn(body.newborn_id)
    return score_child(t.db, nb, _check_payload(body, nb))


@router.post("/checks", response_model=ChildCheckCreatedOut, status_code=201)
def create_check(body: ChildCheckIn, request: Request, background: BackgroundTasks,
                 t: Tenant = Depends(staff("nurse", "doctor"))) -> dict:
    db, user = t.db, t.user
    nb = t.get_newborn(body.newborn_id)
    if nb.status != "active":
        raise HTTPException(409, "Bu bola faol kuzatuvda emas")
    payload = _check_payload(body, nb)
    result = score_child(db, nb, payload)
    old_zone = nb.current_zone
    prior = [c for c in nb.checks if c.check_date <= payload["check_date"]]
    ck = NewbornCheck(newborn_id=nb.id, entered_by=user.id, **{k: payload[k] for k in check_dict(payload)},
                      notes=payload.get("notes"), **check_extras(nb, payload, prior))
    db.add(ck)
    db.flush()
    ra = store_child_assessment(db, nb, ck, result)
    alert = create_alert_if_worse(db, nb, old_zone, ra)
    reopened = after_assessment(db, nb, ra)
    apply_child_assessment(nb, ra)
    refresh_status(nb)
    audit(db, user, "create_child_check", "newborn_check", ck.id, request)
    if alert is not None:
        audit(db, None, "create_alert", "alert", alert.id, request)
    db.commit()
    db.refresh(ck)
    background.add_task(generate_cached, ra.id)
    for a in ([alert] if alert is not None else []) + reopened:
        background.add_task(notify_new_alert_job, a.id)
    return {"check": ck, "assessment": risk_out(ra), "previous_zone": old_zone,
            "alert": alert_out(alert, db) if alert else None}
