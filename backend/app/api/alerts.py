from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import select

from app.api.deps import audit
from app.api.tenancy import Tenant, staff
from app.config import get_settings
from app.models import Alert, User, utcnow
from app.risk import thresholds as T
from app.schemas import ActionIn, AlertOut, ConfirmIn, ContactAttemptIn, ReassignIn, ResolveIn
from app.services import closed_loop as cl
from app.services.ai_summary import build_and_store, generate_cached, get_cached, is_pending
from app.services.alerts import ACK_ROLES, ACTIVE, UNRESOLVED, alert_out, by_subject, record_event, sla_delta
from app.services.notify import notify_admin_count, notify_escalated, notify_reassigned

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
    elif status == "unresolved":
        stmt = stmt.where(Alert.status.in_(UNRESOLVED))
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


@router.get("/action-catalog")
def action_catalog(_: Tenant = Depends(staff())) -> dict:
    """Structured closure: action codes (the same catalog the AI summary uses), outcomes, contact options."""
    from app.llm.actions import ACTIONS

    return {"actions": [{"code": c, "text_uz": txt} for c, txt in ACTIONS.items()],
            "outcomes": [{"code": c, "text_uz": cl.OUTCOME_UZ[c]} for c in T.CLOSURE_OUTCOMES],
            "channels": [{"code": c, "text_uz": txt} for c, txt in cl.CHANNEL_UZ.items()],
            "results": [{"code": c, "text_uz": txt} for c, txt in cl.RESULT_UZ.items()],
            "counselling": [{"code": c, "text_uz": txt, "required": c in cl.REQUIRED_COUNSELLING}
                            for c, txt in cl.COUNSELLING_UZ.items()],
            "refusal_note_min": cl.REFUSAL_NOTE_MIN}


@router.get("/assignees")
def assignees(t: Tenant = Depends(staff("department_head"))) -> list[dict]:
    """Specialists of this polyclinic the department head may reassign an alert to."""
    users = t.db.scalars(select(User).where(User.role == "specialist", User.polyclinic_id == t.polyclinic_id)
                         .order_by(User.full_name)).all()
    return [{"id": u.id, "full_name": u.full_name} for u in users]


def naive_utc(dt: datetime | None) -> datetime | None:
    """Client datetimes -> naive UTC (the DB stores naive UTC)."""
    if dt is None or dt.tzinfo is None:
        return dt
    return dt.astimezone(UTC).replace(tzinfo=None)


def _loop(fn, *args) -> object:
    try:
        return fn(*args)
    except cl.LoopError as e:
        raise HTTPException(e.status, e.message) from e


def _send(t: Tenant, a: Alert, notes: list) -> None:
    for kind, user in notes:
        if kind == "admin":
            notify_admin_count(t.db, a, user)
        else:
            notify_escalated(t.db, a, user)


@router.post("/{alert_id}/ack", response_model=AlertOut)
def ack_alert(alert_id: int, body: ActionIn, request: Request, t: Tenant = Depends(staff(*ACK_ROLES))) -> dict:
    """Acknowledge = "I am on it": stops the current escalation step only. A new measurement becomes due."""
    a = t.get_alert(alert_id)
    _loop(cl.acknowledge, t.db, a, t.user, body.action_taken.strip())
    audit(t.db, t.user, "ack_alert", "alert", a.id, request)
    t.db.commit()
    return alert_out(a, t.db)


@router.post("/{alert_id}/resolve", response_model=AlertOut)
def resolve_alert(alert_id: int, body: ResolveIn, request: Request, t: Tenant = Depends(staff(*ACK_ROLES))) -> dict:
    """Close only with a NEW measurement + action codes + outcome. RED -> "pending_confirmation" (2nd person)."""
    a = t.get_alert(alert_id)
    _loop(cl.resolve, t.db, a, t.user, body.action_codes, body.outcome, body.note)
    audit(t.db, t.user, "resolve_alert" if a.status == "resolved" else "propose_resolution", "alert", a.id, request)
    t.db.commit()
    return alert_out(a, t.db)


@router.post("/{alert_id}/confirm", response_model=AlertOut)
def confirm_closure(alert_id: int, body: ConfirmIn, request: Request,
                    t: Tenant = Depends(staff(*T.RED_CLOSURE_CONFIRM_ROLES))) -> dict:
    """Two-person rule for RED: a DIFFERENT doctor / department head confirms (approve) or returns the closure."""
    a = t.get_alert(alert_id)
    _loop(cl.confirm, t.db, a, t.user, body.approve, body.note)
    audit(t.db, t.user, "confirm_closure" if body.approve else "return_closure", "alert", a.id, request)
    t.db.commit()
    return alert_out(a, t.db)


@router.post("/{alert_id}/contact-attempts", response_model=AlertOut, status_code=201)
def add_contact_attempt(alert_id: int, body: ContactAttemptIn, request: Request,
                        t: Tenant = Depends(staff("nurse", "doctor"))) -> dict:
    """"Aloqa urinishi qo'shish": may mark the alert "unreachable" (still active) and escalate it."""
    a = t.get_alert(alert_id)
    at = naive_utc(body.attempted_at)
    notes = _loop(cl.add_contact_attempt, t.db, a, t.user, body.channel, body.result, body.note,
                  body.counselling, at)
    audit(t.db, t.user, "contact_attempt", "alert", a.id, request)
    t.db.commit()
    _send(t, a, notes)
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
    if a.status == "acknowledged":  # the "new measurement due" deadline (closed loop)
        a.measurement_due_at = utcnow()
    elif a.status in ACTIVE:
        a.sla_due_at = utcnow()
    else:
        raise HTTPException(409, "Faqat faol ogohlantirish uchun")
    audit(t.db, t.user, "demo_expire_sla", "alert", a.id, request)
    t.db.commit()
    return alert_out(a, t.db)
