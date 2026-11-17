"""Alert serialization and SLA escalation (specialist -> district doctor -> regional admin)."""
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Alert, User, utcnow
from app.risk.features import gest_weeks


def alert_out(a: Alert, db: Session) -> dict:
    preg = a.pregnancy
    pat = preg.patient if preg else None
    ra = a.risk_assessment
    assignee = db.get(User, a.assigned_user_id) if a.assigned_user_id else None
    visit_date = a.created_at.date()
    return {
        "id": a.id, "level": a.level, "status": a.status, "escalation_level": a.escalation_level,
        "sla_due_at": a.sla_due_at, "created_at": a.created_at, "acknowledged_at": a.acknowledged_at,
        "resolved_at": a.resolved_at, "action_taken": a.action_taken,
        "assigned_to": assignee.full_name if assignee else None,
        "pregnancy_id": preg.id if preg else None, "patient_id": pat.id if pat else None,
        "patient_code": pat.code if pat else None,
        "gestational_weeks": gest_weeks(preg.lmp_date, visit_date) if preg else None,
        "district_name": pat.district.name if pat else None,
        "reasons": [h["uz_text"] for h in (ra.rule_hits + ra.trend_hits)][:4] if ra else [],
    }


def _next_assignee(db: Session, alert: Alert, level: int) -> User | None:
    district = alert.pregnancy.patient.district
    if level == 1:
        return db.scalars(select(User).where(User.role == "doctor", User.district_id == district.id)).first()
    return db.scalars(select(User).where(User.role == "admin", User.region_id == district.region_id)).first()


def run_escalations(db: Session) -> int:
    """Escalate every open/escalated alert past its SLA. Returns the number escalated."""
    s = get_settings()
    now = utcnow()
    overdue = db.scalars(select(Alert).where(Alert.status.in_(("open", "escalated")), Alert.sla_due_at < now,
                                             Alert.escalation_level < 2)).all()
    for a in overdue:
        a.escalation_level += 1
        a.status = "escalated"
        nxt = _next_assignee(db, a, a.escalation_level)
        if nxt is not None:
            a.assigned_user_id = nxt.id
        a.sla_due_at = now + (timedelta(minutes=s.effective_sla_red_minutes) if a.level == "red"
                              else timedelta(hours=s.sla_yellow_hours))
    if overdue:
        db.commit()
    return len(overdue)
