from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import select

from app.api.deps import audit
from app.api.tenancy import Tenant, staff
from app.config import get_settings
from app.models import Alert, User, utcnow
from app.schemas import ActionIn, AlertOut, ReassignIn
from app.services.ai_summary import build_and_store, generate_cached, get_cached, is_pending
from app.services.alerts import ACK_ROLES, ACTIVE, alert_out, by_subject, record_event, sla_delta
from app.services.notify import notify_reassigned

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


def ensure_summaries(t: Tenant, alerts: list[Alert], background: BackgroundTasks) -> None:
    """Active alerts without a (current-version) summary: the template is built inline (instant, offline);
    with Gemini enabled it is generated in the background and the alert says summary_status "pending"."""
    llm = get_settings().llm_enabled
    for a in alerts:
        if a.status not in ACTIVE or get_cached(t.db, a.risk_assessment_id) is not None:
            continue
        if not llm:
            build_and_store(t.db, a.risk_assessment)
        elif not is_pending(a.risk_assessment_id):
            background.add_task(generate_cached, a.risk_assessment_id)


@router.get("", response_model=list[AlertOut])
def list_alerts(background: BackgroundTasks, status: str | None = None, level: str | None = None,
                mine: bool = False, escalated: bool = False, subject: str | None = None, limit: int = 200,
                t: Tenant = Depends(staff())) -> list[dict]:
    """subject: pregnancy | child | all (default all)."""
    db = t.db
    stmt = by_subject(t.alerts(select(Alert)), subject)
    if status == "active":
        stmt = stmt.where(Alert.status.in_(ACTIVE))
    elif status:
        stmt = stmt.where(Alert.status == status)
    if level:
        stmt = stmt.where(Alert.level == level)
    if mine:
        stmt = stmt.where(Alert.assigned_user_id == t.user.id)
    if escalated:  # "Kechikkan ogohlantirishlar": escalated past the specialist
        stmt = stmt.where(Alert.escalation_level >= 1)
    alerts = db.scalars(stmt.order_by(Alert.created_at.desc()).limit(min(limit, 500))).all()
    ensure_summaries(t, list(alerts), background)
    return [alert_out(a, db) for a in alerts]


@router.get("/assignees")
def assignees(t: Tenant = Depends(staff("department_head"))) -> list[dict]:
    """Specialists of this polyclinic the department head may reassign an alert to."""
    users = t.db.scalars(select(User).where(User.role == "specialist", User.polyclinic_id == t.polyclinic_id)
                         .order_by(User.full_name)).all()
    return [{"id": u.id, "full_name": u.full_name} for u in users]


@router.post("/{alert_id}/ack", response_model=AlertOut)
def ack_alert(alert_id: int, body: ActionIn, request: Request, t: Tenant = Depends(staff(*ACK_ROLES))) -> dict:
    a = t.get_alert(alert_id)
    if a.status not in ACTIVE:
        raise HTTPException(409, "Ogohlantirish allaqachon qabul qilingan")
    a.status, a.acknowledged_at, a.action_taken = "acknowledged", utcnow(), body.action_taken.strip()
    a.assigned_user_id = t.user.id
    record_event(t.db, a, "acknowledged", assignee_id=t.user.id, actor_id=t.user.id, note=a.action_taken[:300])
    audit(t.db, t.user, "ack_alert", "alert", a.id, request)
    t.db.commit()
    return alert_out(a, t.db)


@router.post("/{alert_id}/resolve", response_model=AlertOut)
def resolve_alert(alert_id: int, body: ActionIn, request: Request, t: Tenant = Depends(staff(*ACK_ROLES))) -> dict:
    a = t.get_alert(alert_id)
    if a.status == "resolved":
        raise HTTPException(409, "Ogohlantirish allaqachon yopilgan")
    now = utcnow()
    a.acknowledged_at = a.acknowledged_at or now
    a.status, a.resolved_at = "resolved", now
    a.action_taken = ((a.action_taken + " | ") if a.action_taken else "") + body.action_taken.strip()
    record_event(t.db, a, "resolved", assignee_id=a.assigned_user_id, actor_id=t.user.id,
                 note=body.action_taken.strip()[:300])
    audit(t.db, t.user, "resolve_alert", "alert", a.id, request)
    t.db.commit()
    return alert_out(a, t.db)


@router.post("/{alert_id}/reassign", response_model=AlertOut)
def reassign_alert(alert_id: int, body: ReassignIn, request: Request,
                   t: Tenant = Depends(staff("department_head"))) -> dict:
    """Department head hands an active alert back to a specialist of the SAME polyclinic; the SLA restarts."""
    a = t.get_alert(alert_id)
    if a.status not in ACTIVE:
        raise HTTPException(409, "Faqat faol ogohlantirishni qayta biriktirish mumkin")
    target = t.db.get(User, body.user_id)
    if target is None or target.role != "specialist" or target.polyclinic_id != t.polyclinic_id:
        raise HTTPException(404, "Mutaxassis topilmadi")
    a.assigned_user_id = target.id
    a.sla_due_at = utcnow() + sla_delta(a.level)
    record_event(t.db, a, "reassigned", assignee_id=target.id, actor_id=t.user.id,
                 note=(body.note or "").strip()[:300] or None)
    audit(t.db, t.user, "reassign_alert", "alert", a.id, request)
    t.db.commit()
    notify_reassigned(t.db, a, target)
    t.db.commit()
    return alert_out(a, t.db)


@router.post("/{alert_id}/demo-expire-sla", response_model=AlertOut)
def demo_expire_sla(alert_id: int, request: Request, t: Tenant = Depends(staff("specialist", "department_head"))) -> dict:
    """DEMO_MODE only: set this alert's SLA deadline to now, so the next escalation run (<=30 s) escalates it.

    Specialist / department head only: admins never see individual alerts (tenancy rule).
    """
    if not get_settings().demo_mode:
        raise HTTPException(404, "Faqat demo rejimida mavjud")
    a = t.get_alert(alert_id)
    if a.status not in ACTIVE:
        raise HTTPException(409, "Faqat faol ogohlantirish uchun")
    a.sla_due_at = utcnow()
    audit(t.db, t.user, "demo_expire_sla", "alert", a.id, request)
    t.db.commit()
    return alert_out(a, t.db)
