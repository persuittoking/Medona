from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select

from app.api.deps import audit
from app.api.tenancy import Tenant, staff
from app.config import get_settings
from app.models import Alert, Patient, Pregnancy, utcnow
from app.schemas import ActionIn, AlertOut
from app.services.alerts import alert_out

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertOut])
def list_alerts(status: str | None = None, level: str | None = None, mine: bool = False, limit: int = 200,
                t: Tenant = Depends(staff())) -> list[dict]:
    db = t.db
    stmt = (select(Alert).join(Pregnancy, Alert.pregnancy_id == Pregnancy.id)
            .join(Patient, Pregnancy.patient_id == Patient.id))
    stmt = t.patients(stmt)
    if status == "active":
        stmt = stmt.where(Alert.status.in_(("open", "escalated")))
    elif status:
        stmt = stmt.where(Alert.status == status)
    if level:
        stmt = stmt.where(Alert.level == level)
    if mine:
        stmt = stmt.where(Alert.assigned_user_id == t.user.id)
    alerts = db.scalars(stmt.order_by(Alert.created_at.desc()).limit(min(limit, 500))).all()
    return [alert_out(a, db) for a in alerts]


@router.post("/{alert_id}/ack", response_model=AlertOut)
def ack_alert(alert_id: int, body: ActionIn, request: Request, t: Tenant = Depends(staff("specialist", "doctor"))) -> dict:
    a = t.get_alert(alert_id)
    if a.status not in ("open", "escalated"):
        raise HTTPException(409, "Ogohlantirish allaqachon qabul qilingan")
    a.status, a.acknowledged_at, a.action_taken = "acknowledged", utcnow(), body.action_taken.strip()
    a.assigned_user_id = t.user.id
    audit(t.db, t.user, "ack_alert", "alert", a.id, request)
    t.db.commit()
    return alert_out(a, t.db)


@router.post("/{alert_id}/resolve", response_model=AlertOut)
def resolve_alert(alert_id: int, body: ActionIn, request: Request,
                  t: Tenant = Depends(staff("specialist", "doctor"))) -> dict:
    a = t.get_alert(alert_id)
    if a.status == "resolved":
        raise HTTPException(409, "Ogohlantirish allaqachon yopilgan")
    now = utcnow()
    a.acknowledged_at = a.acknowledged_at or now
    a.status, a.resolved_at = "resolved", now
    a.action_taken = ((a.action_taken + " | ") if a.action_taken else "") + body.action_taken.strip()
    audit(t.db, t.user, "resolve_alert", "alert", a.id, request)
    t.db.commit()
    return alert_out(a, t.db)


@router.post("/{alert_id}/demo-expire-sla", response_model=AlertOut)
def demo_expire_sla(alert_id: int, request: Request, t: Tenant = Depends(staff("specialist"))) -> dict:
    """DEMO_MODE only: set this alert's SLA deadline to now, so the next escalation run (<=30 s) escalates it.

    Specialist only: admins never see individual alerts (tenancy rule), so they have no row to press it on.
    """
    if not get_settings().demo_mode:
        raise HTTPException(404, "Faqat demo rejimida mavjud")
    a = t.get_alert(alert_id)
    if a.status not in ("open", "escalated"):
        raise HTTPException(409, "Faqat faol ogohlantirish uchun")
    a.sla_due_at = utcnow()
    audit(t.db, t.user, "demo_expire_sla", "alert", a.id, request)
    t.db.commit()
    return alert_out(a, t.db)
