from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import audit, can_access_patient, current_user, require_roles, scope_patients
from app.db import get_db
from app.models import Alert, Patient, Pregnancy, User, utcnow
from app.schemas import ActionIn, AlertOut
from app.services.alerts import alert_out, run_escalations

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertOut])
def list_alerts(status: str | None = None, level: str | None = None, mine: bool = False, limit: int = 200,
                user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    run_escalations(db)
    stmt = (select(Alert).join(Pregnancy, Alert.pregnancy_id == Pregnancy.id)
            .join(Patient, Pregnancy.patient_id == Patient.id))
    stmt = scope_patients(stmt, user)
    if status == "active":
        stmt = stmt.where(Alert.status.in_(("open", "escalated")))
    elif status:
        stmt = stmt.where(Alert.status == status)
    if level:
        stmt = stmt.where(Alert.level == level)
    if mine:
        stmt = stmt.where(Alert.assigned_user_id == user.id)
    alerts = db.scalars(stmt.order_by(Alert.created_at.desc()).limit(min(limit, 500))).all()
    return [alert_out(a, db) for a in alerts]


def _get_alert(db: Session, alert_id: int, user: User) -> Alert:
    a = db.get(Alert, alert_id)
    if a is None:
        raise HTTPException(404, "Ogohlantirish topilmadi")
    if not can_access_patient(user, a.pregnancy.patient):
        raise HTTPException(403, "Ruxsat yo'q")
    return a


@router.post("/{alert_id}/ack", response_model=AlertOut)
def ack_alert(alert_id: int, body: ActionIn, request: Request,
              user: User = Depends(require_roles("specialist", "doctor", "admin")), db: Session = Depends(get_db)) -> dict:
    a = _get_alert(db, alert_id, user)
    if a.status not in ("open", "escalated"):
        raise HTTPException(409, "Ogohlantirish allaqachon qabul qilingan")
    a.status, a.acknowledged_at, a.action_taken = "acknowledged", utcnow(), body.action_taken.strip()
    a.assigned_user_id = user.id
    audit(db, user, "ack_alert", "alert", a.id, request)
    db.commit()
    return alert_out(a, db)


@router.post("/{alert_id}/resolve", response_model=AlertOut)
def resolve_alert(alert_id: int, body: ActionIn, request: Request,
                  user: User = Depends(require_roles("specialist", "doctor", "admin")), db: Session = Depends(get_db)) -> dict:
    a = _get_alert(db, alert_id, user)
    if a.status == "resolved":
        raise HTTPException(409, "Ogohlantirish allaqachon yopilgan")
    now = utcnow()
    a.acknowledged_at = a.acknowledged_at or now
    a.status, a.resolved_at = "resolved", now
    a.action_taken = ((a.action_taken + " | ") if a.action_taken else "") + body.action_taken.strip()
    audit(db, user, "resolve_alert", "alert", a.id, request)
    db.commit()
    return alert_out(a, db)
