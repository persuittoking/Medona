"""Alert escalation chain, SLA, history events and serialization — the ONE place the chain is defined.

RED:    specialist (level 0) -> OvaBMU department head (level 1) -> district admin, count only (level 2)
YELLOW: specialist (level 0) -> polyclinic doctor (level 1)       -> district admin, count only (level 2)
Each step waits one SLA period (RED: SLA_RED_MINUTES, or DEMO_SLA_RED_MINUTES in DEMO_MODE; YELLOW:
SLA_YELLOW_HOURS). Admins never get patient-level access: at level 2 the patient stays assigned to the level-1
person and the district admin only receives an aggregate count (Telegram).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import ADMIN_ROLES, Alert, AlertEvent, AuditLog, Newborn, Patient, Polyclinic, Pregnancy, User, utcnow
from app.risk.features import gest_weeks
from app.risk.infant import age_days, age_text
from app.risk.trends import is_predictive

ESCALATION_CHAIN: dict[str, tuple[str, ...]] = {
    "red": ("specialist", "department_head", "district_admin"),
    "yellow": ("specialist", "doctor", "district_admin"),
}
MAX_ESCALATION_LEVEL = 2
NOTIFY_ONLY_ROLES = set(ADMIN_ROLES)  # notified with a count, never assigned a patient
ACTIVE = ("open", "escalated")
ACK_ROLES = ("specialist", "doctor", "department_head")


def sla_delta(level: str) -> timedelta:
    s = get_settings()
    return timedelta(minutes=s.effective_sla_red_minutes) if level == "red" else timedelta(hours=s.sla_yellow_hours)


SUBJECTS = ("pregnancy", "child", "all")


def polyclinic_alerts(stmt: Select, polyclinic_id: int) -> Select:
    """Restrict an Alert statement to one polyclinic, whatever the subject (pregnancy or child)."""
    stmt = (stmt.outerjoin(Pregnancy, Alert.pregnancy_id == Pregnancy.id)
            .outerjoin(Patient, Pregnancy.patient_id == Patient.id)
            .outerjoin(Newborn, Alert.newborn_id == Newborn.id))
    return stmt.where(or_(Patient.polyclinic_id == polyclinic_id, Newborn.polyclinic_id == polyclinic_id))


def by_subject(stmt: Select, subject: str | None) -> Select:
    if subject == "pregnancy":
        return stmt.where(Alert.pregnancy_id.is_not(None))
    if subject == "child":
        return stmt.where(Alert.newborn_id.is_not(None))
    return stmt


def alert_polyclinic(a: Alert) -> Polyclinic:
    """Tenant polyclinic of the alert's subject (pregnancy -> mother; child -> copied from the mother)."""
    return a.pregnancy.patient.polyclinic if a.pregnancy is not None else a.newborn.polyclinic


def subject_info(a: Alert) -> dict:
    """Who the alert is about, for lists and messages: "Homilador · 32 hafta" or "Bola · 4 oy" (no PII)."""
    on = a.created_at.date()
    if a.newborn is not None:
        nb = a.newborn
        mother = nb.pregnancy.patient
        days = age_days(nb.birth_date, on)
        return {"subject": "child", "newborn_id": nb.id, "code": nb.code, "patient_id": mother.id,
                "pregnancy_id": None, "gestational_weeks": None, "child_age_days": days,
                "subject_label": f"Bola · {age_text(days)}", "mahalla_name": mother.mahalla.name}
    preg = a.pregnancy
    pat = preg.patient
    gw = gest_weeks(preg.lmp_date, on)
    return {"subject": "pregnancy", "newborn_id": None, "code": pat.code, "patient_id": pat.id,
            "pregnancy_id": preg.id, "gestational_weeks": gw, "child_age_days": None,
            "subject_label": f"Homilador · {int(gw)} hafta", "mahalla_name": pat.mahalla.name}


def chain_role(level: str, escalation_level: int) -> str:
    chain = ESCALATION_CHAIN[level]
    return chain[min(escalation_level, len(chain) - 1)]


def role_user(db: Session, role: str, polyclinic_id: int, district_id: int) -> User | None:
    if role in NOTIFY_ONLY_ROLES:
        return db.scalars(select(User).where(User.role == role, User.district_id == district_id)
                          .order_by(User.id)).first()
    return db.scalars(select(User).where(User.role == role, User.polyclinic_id == polyclinic_id)
                      .order_by(User.id)).first()


def first_assignee(db: Session, polyclinic_id: int, district_id: int, level: str) -> User | None:
    return role_user(db, chain_role(level, 0), polyclinic_id, district_id)


def record_event(db: Session, alert: Alert, event: str, *, assignee_id: int | None = None,
                 actor_id: int | None = None, note: str | None = None, at: datetime | None = None) -> None:
    db.add(AlertEvent(alert_id=alert.id, event=event, escalation_level=alert.escalation_level,
                      assignee_id=assignee_id, actor_id=actor_id, note=note, created_at=at or utcnow()))


# ---------------- serialization ----------------
def _history(db: Session, a: Alert) -> list[dict]:
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(
        {e.assignee_id for e in a.events} | {e.actor_id for e in a.events}))).all()} if a.events else {}
    out = []
    for e in a.events:
        who, actor = users.get(e.assignee_id), users.get(e.actor_id)
        out.append({"at": e.created_at, "event": e.event, "escalation_level": e.escalation_level,
                    "assignee": who.full_name if who else None, "assignee_role": who.role if who else None,
                    "actor": actor.full_name if actor else None, "note": e.note})
    return out


def alert_out(a: Alert, db: Session) -> dict:
    from app.services.ai_summary import alert_summary  # lazy: ai_summary -> scoring -> alerts

    subj = subject_info(a)
    ra = a.risk_assessment
    assignee = db.get(User, a.assigned_user_id) if a.assigned_user_id else None
    summary = alert_summary(db, a.risk_assessment_id)
    if summary["summary_status"] == "pending" and a.status not in ACTIVE:
        summary["summary_status"] = "unavailable"  # closed alerts are not (re)generated
    ext_pc = None
    if ra is not None:
        if ra.visit is not None and ra.visit.performed_at_polyclinic is not None:
            ext_pc = ra.visit.performed_at_polyclinic
        elif ra.check is not None and ra.check.performed_at_polyclinic is not None:
            ext_pc = ra.check.performed_at_polyclinic
    return {
        "id": a.id, "level": a.level, "status": a.status, "escalation_level": a.escalation_level,
        "sla_due_at": a.sla_due_at, "created_at": a.created_at, "acknowledged_at": a.acknowledged_at,
        "resolved_at": a.resolved_at, "action_taken": a.action_taken,
        "assigned_to": assignee.full_name if assignee else None,
        "assigned_role": assignee.role if assignee else None,
        "assigned_user_id": a.assigned_user_id,
        "next_role": (chain_role(a.level, a.escalation_level + 1)
                      if a.escalation_level < MAX_ESCALATION_LEVEL else None),
        "subject": subj["subject"], "subject_label": subj["subject_label"], "newborn_id": subj["newborn_id"],
        "child_age_days": subj["child_age_days"],
        "pregnancy_id": subj["pregnancy_id"], "patient_id": subj["patient_id"], "patient_code": subj["code"],
        "gestational_weeks": subj["gestational_weeks"], "mahalla_name": subj["mahalla_name"],
        "reasons": [h["uz_text"] for h in (ra.rule_hits + ra.trend_hits) if h["zone"] != "factor"][:4] if ra else [],
        "trend_driven": bool(ra and any(is_predictive(h) for h in ra.trend_hits)),
        **summary,
        "performed_at_polyclinic_name": ext_pc.name if ext_pc else None,
        "external_notice_uz": "Tashqi natija kelib tushdi" if ext_pc else None,
        "history": _history(db, a),
    }


# ---------------- escalation ----------------
def escalate(db: Session, a: Alert, now: datetime) -> list[tuple[str, User | None]]:
    """Move one overdue alert one step up the chain. Returns the notifications to send after commit."""
    poly = alert_polyclinic(a)
    a.escalation_level += 1
    a.status = "escalated"
    a.sla_due_at = now + sla_delta(a.level)
    role = chain_role(a.level, a.escalation_level)
    target = role_user(db, role, poly.id, poly.district_id)
    db.add(AuditLog(user_id=None, action=f"escalate_alert_l{a.escalation_level}", entity="alert", entity_id=a.id))
    if role in NOTIFY_ONLY_ROLES:  # count only; the patient stays with the level-1 assignee
        record_event(db, a, "admin_notified", assignee_id=target.id if target else None, at=now,
                     note="Tuman boshqaruviga faqat soni xabar qilindi")
        return [("admin", target)]
    if target is not None:
        a.assigned_user_id = target.id
    record_event(db, a, "escalated", assignee_id=a.assigned_user_id, at=now)
    return [("escalated", target)]


def run_escalations(db: Session) -> int:
    """Escalate every open/escalated alert past its SLA (one step per run). Returns the number escalated."""
    from app.services import notify  # lazy: notify -> ai_summary -> scoring -> alerts

    now = utcnow()
    overdue = db.scalars(select(Alert).where(Alert.status.in_(ACTIVE), Alert.sla_due_at < now,
                                             Alert.escalation_level < MAX_ESCALATION_LEVEL)).all()
    todo = [(a, escalate(db, a, now)) for a in overdue]
    if overdue:
        db.commit()
    for a, notes in todo:
        for kind, user in notes:
            if kind == "admin":
                notify.notify_admin_count(db, a, user)
            else:
                notify.notify_escalated(db, a, user)
    if todo:
        db.commit()
    return len(overdue)
