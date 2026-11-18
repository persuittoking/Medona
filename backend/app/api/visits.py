from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import select

from app.api.deps import audit
from app.api.tenancy import Tenant, staff
from app.models import AuditLog, Newborn, NewbornCheck, Patient, Polyclinic, Pregnancy, Visit
from app.risk.features import gest_weeks
from app.schemas import (
    ExternalCheckIn,
    ExternalEntryOut,
    ExternalLookupIn,
    ExternalLookupOut,
    ExternalVisitIn,
    RiskOut,
    VisitCreatedOut,
    VisitIn,
    VisitPlanOut,
)
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
from app.services.notify import notify_external_result, notify_new_alert_job
from app.services.scoring import (
    apply_assessment,
    create_alert_if_worse,
    risk_out,
    score_new_visit,
    store_assessment,
)
from app.services.visit_intensity import confirm_light_visit_plan, sync_after_visit

router = APIRouter(prefix="/api", tags=["visits"])


def _visit_payload(body: VisitIn | ExternalVisitIn, lmp: date) -> dict:
    d = body.model_dump(exclude={"pregnancy_id", "pinfl", "patient_code"})
    d["visit_date"] = d["visit_date"] or date.today()
    if d["visit_date"] > date.today():
        raise HTTPException(422, "Tashrif sanasi kelajakda bo'lishi mumkin emas")
    d["gestational_weeks"] = gest_weeks(lmp, d["visit_date"])
    return d


@router.post("/risk/preview", response_model=RiskOut)
def risk_preview(body: VisitIn, t: Tenant = Depends(staff())) -> dict:
    """Score a visit WITHOUT saving anything (live preview while the nurse types)."""
    preg = t.get_pregnancy(body.pregnancy_id)
    return score_new_visit(t.db, preg, _visit_payload(body, preg.lmp_date))


@router.post("/visits", response_model=VisitCreatedOut, status_code=201)
def create_visit(body: VisitIn, request: Request, background: BackgroundTasks,
                 t: Tenant = Depends(staff("nurse", "doctor"))) -> dict:
    db, user = t.db, t.user
    preg = t.get_pregnancy(body.pregnancy_id)
    if preg.status != "active":
        raise HTTPException(409, "Bu homiladorlik faol emas")
    payload = _visit_payload(body, preg.lmp_date)
    result = score_new_visit(db, preg, payload)
    old_zone = preg.current_zone
    visit = Visit(pregnancy_id=preg.id, entered_by=user.id, notes=payload.pop("notes"), **payload)
    db.add(visit)
    db.flush()
    ra = store_assessment(db, preg, visit, result)
    alert = create_alert_if_worse(db, preg, old_zone, ra)
    apply_assessment(preg, ra)
    sync_after_visit(db, preg, ra, actor_id=user.id)
    audit(db, user, "create_visit", "visit", visit.id, request)
    if alert is not None:
        audit(db, None, "create_alert", "alert", alert.id, request)
    db.commit()
    db.refresh(visit)
    background.add_task(generate_cached, ra.id)  # AI summary is ready before the specialist opens the card
    if alert is not None:  # runs after the summary task, so the Telegram message carries the 3 bullets
        background.add_task(notify_new_alert_job, alert.id)
    return {"visit": visit, "assessment": risk_out(ra), "previous_zone": old_zone,
            "alert": alert_out(alert, db) if alert else None}


@router.post("/pregnancies/{pregnancy_id}/visit-intensity/confirm", response_model=VisitPlanOut)
def confirm_pregnancy_visit_intensity(pregnancy_id: int, request: Request,
                                      t: Tenant = Depends(staff("doctor"))) -> dict:
    """Doctor-only confirmation of 'Yengil' visit intensity by pregnancy_id."""
    preg = t.get_pregnancy(pregnancy_id)
    ip = request.client.host if request.client else None
    plan = confirm_light_visit_plan(t.db, preg, t.user, ip=ip)
    t.db.commit()
    return plan


@router.post("/external/lookup", response_model=ExternalLookupOut)
@router.post("/visits/external/lookup", response_model=ExternalLookupOut, include_in_schema=False)
def external_lookup(body: ExternalLookupIn, request: Request,
                    t: Tenant = Depends(staff("nurse", "doctor"))) -> dict:
    """Look up a patient of ANY polyclinic by exact JShShIR. Returns minimum-necessary fields only."""
    pat = t.lookup_by_pinfl(body.pinfl, request)
    active_pregs = [p for p in pat.pregnancies if p.status == "active"]
    children = [
        {"newborn_id": n.id, "code": n.code}
        for p in pat.pregnancies for n in p.newborns if n.status == "active" and n.code
    ]
    return {
        "patient_code": pat.code,
        "responsible_polyclinic_id": pat.polyclinic_id,
        "responsible_polyclinic_code": pat.polyclinic.code,
        "responsible_polyclinic_name": pat.polyclinic.name,
        "mahalla_name": pat.mahalla.name,
        "has_active_pregnancy": len(active_pregs) > 0,
        "children": children,
    }


@router.post("/external/visits", response_model=ExternalEntryOut, status_code=201)
@router.post("/visits/external", response_model=ExternalEntryOut, status_code=201, include_in_schema=False)
def create_external_visit(body: ExternalVisitIn, request: Request, background: BackgroundTasks,
                          t: Tenant = Depends(staff("nurse", "doctor"))) -> dict:
    """Record a visit/analysis at an external polyclinic; scored and stored under the responsible clinic."""
    db, user = t.db, t.user
    preg = t.resolve_external_pregnancy(pinfl=body.pinfl, pregnancy_id=body.pregnancy_id, patient_code=body.patient_code)
    pat = preg.patient
    from_pc = db.get(Polyclinic, t.polyclinic_id)
    performed_id = t.polyclinic_id if pat.polyclinic_id != t.polyclinic_id else None
    payload = _visit_payload(body, preg.lmp_date)
    result = score_new_visit(db, preg, payload)
    old_zone = preg.current_zone
    visit = Visit(pregnancy_id=preg.id, entered_by=user.id, performed_at_polyclinic_id=performed_id,
                  notes=payload.pop("notes"), **payload)
    db.add(visit)
    db.flush()
    ra = store_assessment(db, preg, visit, result)
    alert = create_alert_if_worse(db, preg, old_zone, ra)
    apply_assessment(preg, ra)
    sync_after_visit(db, preg, ra, actor_id=user.id)
    ip = request.client.host if request.client else None
    db.add(AuditLog(
        user_id=user.id, action="external_entry", entity="visit", entity_id=visit.id,
        from_polyclinic_id=t.polyclinic_id, to_polyclinic_id=pat.polyclinic_id,
        details=f"from_polyclinic_id={t.polyclinic_id},to_polyclinic_id={pat.polyclinic_id}", ip=ip,
    ))
    if alert is not None:
        audit(db, None, "create_alert", "alert", alert.id, request)
    if performed_id is not None:
        notify_external_result(db, pat, from_pc, visit.id, pat.code)
    db.commit()
    background.add_task(generate_cached, ra.id)
    if alert is not None:
        background.add_task(notify_new_alert_job, alert.id)
    return {
        "id": visit.id,
        "subject": "pregnancy",
        "patient_code": pat.code,
        "responsible_polyclinic_id": pat.polyclinic_id,
        "responsible_polyclinic_code": pat.polyclinic.code,
        "responsible_polyclinic_name": pat.polyclinic.name,
        "mahalla_name": pat.mahalla.name,
        "performed_at_polyclinic_id": performed_id,
        "performed_at_polyclinic_name": from_pc.name,
        "message_uz": f"Natija mas'ul poliklinikaga yuborildi: {pat.polyclinic.name}",
    }


@router.post("/external/checks", response_model=ExternalEntryOut, status_code=201)
@router.post("/children/checks/external", response_model=ExternalEntryOut, status_code=201, include_in_schema=False)
def create_external_check(body: ExternalCheckIn, request: Request, background: BackgroundTasks,
                          t: Tenant = Depends(staff("nurse", "doctor"))) -> dict:
    """Record an infant check at an external polyclinic; scored and stored under the responsible clinic."""
    db, user = t.db, t.user
    nb = t.resolve_external_newborn(pinfl=body.pinfl, newborn_id=body.newborn_id, child_code=body.child_code)
    pat = nb.pregnancy.patient
    from_pc = db.get(Polyclinic, t.polyclinic_id)
    performed_id = t.polyclinic_id if pat.polyclinic_id != t.polyclinic_id else None
    d = body.model_dump(exclude={"newborn_id", "pinfl", "child_code"})
    d["check_date"] = d["check_date"] or date.today()
    if d["check_date"] > date.today():
        raise HTTPException(422, "Ko'rik sanasi kelajakda bo'lishi mumkin emas")
    if d["check_date"] < nb.birth_date:
        raise HTTPException(422, "Ko'rik sanasi tug'ilgan sanadan oldin bo'lishi mumkin emas")
    result = score_child(db, nb, d)
    old_zone = nb.current_zone
    prior = [c for c in nb.checks if c.check_date <= d["check_date"]]
    ck = NewbornCheck(newborn_id=nb.id, entered_by=user.id, performed_at_polyclinic_id=performed_id,
                      **{k: d[k] for k in check_dict(d)}, notes=d.get("notes"), **check_extras(nb, d, prior))
    db.add(ck)
    db.flush()
    ra = store_child_assessment(db, nb, ck, result)
    alert = create_alert_if_worse(db, nb, old_zone, ra)
    apply_child_assessment(nb, ra)
    refresh_status(nb)
    ip = request.client.host if request.client else None
    db.add(AuditLog(
        user_id=user.id, action="external_entry", entity="newborn_check", entity_id=ck.id,
        from_polyclinic_id=t.polyclinic_id, to_polyclinic_id=pat.polyclinic_id,
        details=f"from_polyclinic_id={t.polyclinic_id},to_polyclinic_id={pat.polyclinic_id}", ip=ip,
    ))
    if alert is not None:
        audit(db, None, "create_alert", "alert", alert.id, request)
    if performed_id is not None:
        notify_external_result(db, pat, from_pc, ck.id, nb.code or pat.code)
    db.commit()
    background.add_task(generate_cached, ra.id)
    if alert is not None:
        background.add_task(notify_new_alert_job, alert.id)
    return {
        "id": ck.id,
        "subject": "child",
        "patient_code": nb.code or pat.code,
        "responsible_polyclinic_id": pat.polyclinic_id,
        "responsible_polyclinic_code": pat.polyclinic.code,
        "responsible_polyclinic_name": pat.polyclinic.name,
        "mahalla_name": pat.mahalla.name,
        "performed_at_polyclinic_id": performed_id,
        "performed_at_polyclinic_name": from_pc.name,
        "message_uz": f"Natija mas'ul poliklinikaga yuborildi: {pat.polyclinic.name}",
    }


@router.get("/external/notifications")
def external_notifications(limit: int = 20, t: Tenant = Depends(staff())) -> list[dict]:
    """External results received by this (responsible) polyclinic."""
    db = t.db
    v_stmt = (
        select(Visit, Pregnancy, Patient, Polyclinic)
        .join(Pregnancy, Visit.pregnancy_id == Pregnancy.id)
        .join(Patient, Pregnancy.patient_id == Patient.id)
        .join(Polyclinic, Visit.performed_at_polyclinic_id == Polyclinic.id)
        .where(Patient.polyclinic_id == t.polyclinic_id, Visit.performed_at_polyclinic_id.is_not(None))
        .order_by(Visit.id.desc())
        .limit(limit)
    )
    out = []
    for v, preg, pat, from_pc in db.execute(v_stmt).all():
        out.append({
            "kind": "pregnancy", "id": v.id, "patient_id": pat.id, "pregnancy_id": preg.id, "newborn_id": None,
            "code": pat.code, "mahalla": pat.mahalla.name, "visit_date": v.visit_date, "created_at": v.created_at,
            "performed_at_polyclinic_id": from_pc.id, "performed_at_polyclinic_code": from_pc.code,
            "performed_at_polyclinic_name": from_pc.name,
            "notice_uz": "Tashqi natija kelib tushdi",
            "badge_uz": f"Boshqa poliklinikada o'tkazilgan: {from_pc.name}",
        })
    c_stmt = (
        select(NewbornCheck, Newborn, Patient, Polyclinic)
        .join(Newborn, NewbornCheck.newborn_id == Newborn.id)
        .join(Pregnancy, Newborn.pregnancy_id == Pregnancy.id)
        .join(Patient, Pregnancy.patient_id == Patient.id)
        .join(Polyclinic, NewbornCheck.performed_at_polyclinic_id == Polyclinic.id)
        .where(Newborn.polyclinic_id == t.polyclinic_id, NewbornCheck.performed_at_polyclinic_id.is_not(None))
        .order_by(NewbornCheck.id.desc())
        .limit(limit)
    )
    for ck, nb, pat, from_pc in db.execute(c_stmt).all():
        out.append({
            "kind": "child", "id": ck.id, "patient_id": pat.id, "pregnancy_id": None, "newborn_id": nb.id,
            "code": nb.code, "mahalla": pat.mahalla.name, "visit_date": ck.check_date, "created_at": ck.created_at,
            "performed_at_polyclinic_id": from_pc.id, "performed_at_polyclinic_code": from_pc.code,
            "performed_at_polyclinic_name": from_pc.name,
            "notice_uz": "Tashqi natija kelib tushdi",
            "badge_uz": f"Boshqa poliklinikada o'tkazilgan: {from_pc.name}",
        })
    out.sort(key=lambda r: r["created_at"], reverse=True)
    return out[:limit]
