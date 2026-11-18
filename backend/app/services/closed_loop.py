"""Proof of care (task 12): the system trusts MEASUREMENTS and independent signals, not clicks.

- "Qabul qildim" (acknowledge) stops the current escalation step only; a new measurement becomes due.
- Closing needs a NEW visit / infant check saved after the alert, with the fields relevant to its rules
  (thresholds.CLOSURE_FIELDS), plus structured action codes and an outcome.
- RED: the resolver's closure waits in "pending_confirmation" until a DIFFERENT doctor / department head confirms.
- The first assessment after closure is checked: still RED -> the alert reopens automatically.
- Contact attempts: 3 failed attempts over >= 2 days, or a family refusal, -> status "unreachable" (still active)
  + escalation to the next role + a retry schedule until a measurement arrives.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm.actions import ACTIONS
from app.models import (
    Alert,
    AuditLog,
    ContactAttempt,
    Mahalla,
    Newborn,
    NewbornCheck,
    Patient,
    Pregnancy,
    RiskAssessment,
    User,
    Visit,
    utcnow,
)
from app.risk import thresholds as T
from app.services.alerts import (
    ACTIVE,
    MAX_ESCALATION_LEVEL,
    UNRESOLVED,
    escalate,
    first_assignee,
    record_event,
    sla_delta,
)

OUTCOME_UZ = {"improved": "Yaxshilandi", "unchanged": "O'zgarishsiz", "referred": "Yo'llandi"}
CHANNEL_UZ = {"home_visit": "Uyga borildi", "phone": "Telefon", "telegram": "Telegram",
              "mahalla": "Mahalla vakili orqali"}
RESULT_UZ = {"reached": "Aloqa bo'ldi", "refused": "Oila ruxsat bermadi", "elsewhere": "Bemor boshqa joyda",
             "not_found": "Topilmadi", "phone_off": "Telefon o'chiq"}
COUNSELLING_UZ = {
    "danger_signs": "Xavfli belgilar va kechikish oqibatlari tushuntirildi",
    "mahalla_activist": "Mahalladagi xotin-qizlar faoli jalb qilindi",
    "mahalla_leader": "Mahalla raisi jalb qilindi",
    "another_time": "Boshqa vaqtda uyga tashrif taklif qilindi",
}
REQUIRED_COUNSELLING = ("danger_signs",)
REFUSAL_NOTE_MIN = 10
FIELD_UZ = {
    "systolic": "arterial bosim (sistolik)", "diastolic": "arterial bosim (diastolik)",
    "hemoglobin_g_l": "gemoglobin", "fetal_heart_rate": "homila yurak urishi", "temperature_c": "harorat",
    "fasting_glucose_mmol": "glyukoza (och qoringa)", "weight_kg": "vazn", "fundal_height_cm": "bachadon tubi balandligi",
    "resp_rate": "nafas soni", "weight_g": "bola vazni", "vaccines_given": "emlash",
}
NEED_MEASUREMENT_UZ = "Yopish uchun yangi o'lchov kerak"


class LoopError(Exception):
    """A closed-loop rule was violated; `status` is the HTTP status the API should return."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


# ---------------- measurement evidence ----------------
def required_fields(a: Alert) -> list[str]:
    """Union of the measured fields required by the rules that raised the alert ([] = any new record)."""
    ra = a.risk_assessment
    hits = [h for h in (ra.rule_hits + ra.trend_hits) if h.get("zone") != "factor"] if ra else []
    fields: list[str] = []
    mapped = False
    for h in hits:
        if h.get("code") in T.CLOSURE_FIELDS:
            mapped = True
            fields += [f for f in T.CLOSURE_FIELDS[h["code"]] if f not in fields]
    if not mapped:
        fields = list(T.CLOSURE_DEFAULT_FIELDS["child" if a.newborn_id else "pregnancy"])
    return fields


def _has(record: Visit | NewbornCheck, fields: list[str]) -> bool:
    for f in fields:
        v = getattr(record, f, None)
        if v is None or (isinstance(v, list) and not v):
            return False
    return True


def candidate_records(db: Session, a: Alert) -> list[Visit | NewbornCheck]:
    """Visits / checks of the alert's subject saved AFTER the alert (newest first). The record that raised the
    alert never counts; ids are also compared so older rows with a later created_at (seed data) do not count."""
    ra = a.risk_assessment
    if a.pregnancy_id is not None:
        stmt = select(Visit).where(Visit.pregnancy_id == a.pregnancy_id, Visit.created_at > a.created_at)
        if ra is not None and ra.visit_id is not None:
            stmt = stmt.where(Visit.id > ra.visit_id)
        return list(db.scalars(stmt.order_by(Visit.id.desc())).all())
    stmt = select(NewbornCheck).where(NewbornCheck.newborn_id == a.newborn_id, NewbornCheck.created_at > a.created_at)
    if ra is not None and ra.check_id is not None:
        stmt = stmt.where(NewbornCheck.id > ra.check_id)
    return list(db.scalars(stmt.order_by(NewbornCheck.id.desc())).all())


def find_evidence(db: Session, a: Alert) -> Visit | NewbornCheck | None:
    fields = required_fields(a)
    return next((r for r in candidate_records(db, a) if _has(r, fields)), None)


def measurement_due(level: str) -> timedelta:
    return timedelta(hours=T.MEASUREMENT_DUE_HOURS.get(level, 24))


# ---------------- acknowledge / resolve / confirm ----------------
def acknowledge(db: Session, a: Alert, user: User, note: str) -> None:
    """Stops the CURRENT escalation step only. The alert stays unresolved until a measurement + closure."""
    if a.status not in ACTIVE:
        raise LoopError(409, "Ogohlantirish allaqachon qabul qilingan")
    now = utcnow()
    a.status, a.acknowledged_at, a.action_taken = "acknowledged", now, note
    a.assigned_user_id = user.id
    a.measurement_due_at = now + measurement_due(a.level)
    record_event(db, a, "acknowledged", assignee_id=user.id, actor_id=user.id, note=note[:300])


def resolve(db: Session, a: Alert, user: User, codes: list[str], outcome: str, note: str | None) -> None:
    if a.status == "resolved":
        raise LoopError(409, "Ogohlantirish allaqachon yopilgan")
    if a.status == "pending_confirmation":
        raise LoopError(409, "Yopish boshqa xodim tasdig'ini kutmoqda")
    codes = [c.strip().upper() for c in codes]
    bad = [c for c in codes if c not in ACTIONS]
    if not codes or bad:
        raise LoopError(422, "Katalogdagi kamida bitta chora tanlang" + (f" (noma'lum: {', '.join(bad)})" if bad else ""))
    if outcome not in T.CLOSURE_OUTCOMES:
        raise LoopError(422, "Natija noto'g'ri")
    ev = find_evidence(db, a)
    if ev is None:
        raise LoopError(409, NEED_MEASUREMENT_UZ)
    now = utcnow()
    a.acknowledged_at = a.acknowledged_at or now
    a.resolved_at, a.resolved_by_id = now, user.id
    a.resolution_action_codes, a.resolution_outcome = codes, outcome
    a.evidence_visit_id = ev.id if isinstance(ev, Visit) else None
    a.evidence_check_id = ev.id if isinstance(ev, NewbornCheck) else None
    a.confirmed_by_id, a.confirmed_at, a.retry_due_at = None, None, None
    text = f"{OUTCOME_UZ[outcome]}: " + "; ".join(ACTIONS[c] for c in codes)
    if note and note.strip():
        text += f" ({note.strip()})"
    a.action_taken = ((a.action_taken + " | ") if a.action_taken else "") + text
    if a.level == "red":
        a.status = "pending_confirmation"
        record_event(db, a, "resolution_proposed", assignee_id=a.assigned_user_id, actor_id=user.id, note=text[:300])
    else:
        a.status = "resolved"
        record_event(db, a, "resolved", assignee_id=a.assigned_user_id, actor_id=user.id, note=text[:300])


def confirm(db: Session, a: Alert, user: User, approve: bool, note: str | None) -> None:
    """Two-person rule for RED: a DIFFERENT doctor / department head confirms (or returns) the closure."""
    if a.status != "pending_confirmation":
        raise LoopError(409, "Tasdiqlash kutilayotgan yopish yo'q")
    if user.role not in T.RED_CLOSURE_CONFIRM_ROLES:
        raise LoopError(403, "Faqat shifokor yoki bo'lim mudiri tasdiqlaydi")
    if user.id == a.resolved_by_id:
        raise LoopError(409, "Yopishni boshqa xodim tasdiqlashi kerak (ikki kishi qoidasi)")
    now = utcnow()
    msg = (note or "").strip()[:300] or None
    if approve:
        a.status, a.confirmed_by_id, a.confirmed_at = "resolved", user.id, now
        record_event(db, a, "resolved", assignee_id=a.assigned_user_id, actor_id=user.id,
                     note=msg or "Yopish tasdiqlandi (ikki kishi qoidasi)")
    else:
        a.status, a.resolved_at, a.resolved_by_id = "acknowledged", None, None
        a.measurement_due_at = now + measurement_due(a.level)
        record_event(db, a, "closure_returned", assignee_id=a.assigned_user_id, actor_id=user.id, note=msg)


# ---------------- after every saved visit / check ----------------
def _subject_filter(subject: Pregnancy | Newborn):
    return (Alert.pregnancy_id == subject.id) if isinstance(subject, Pregnancy) else (Alert.newborn_id == subject.id)


def after_assessment(db: Session, subject: Pregnancy | Newborn, ra: RiskAssessment) -> list[Alert]:
    """Call after a new visit / check was scored and stored. Returns the alerts that were REOPENED (to notify)."""
    now = utcnow()
    new_id = _new_alert_id(db, ra)
    alerts = list(db.scalars(select(Alert).where(_subject_filter(subject), Alert.id != new_id)
                             .order_by(Alert.id.desc())).all())
    record = ra.visit or ra.check
    for a in alerts:  # a new qualifying measurement for an unresolved alert
        if a.status in ("acknowledged", *ACTIVE) and record is not None and _has(record, required_fields(a)):
            note = "Yangi o'lchov kiritildi — endi yopish mumkin"
            if a.status == "unreachable":
                a.status = "acknowledged"
                a.acknowledged_at = a.acknowledged_at or now
                note = "Yangi o'lchov kiritildi: bemor bilan aloqa o'rnatildi"
            a.retry_due_at = a.measurement_due_at = None
            record_event(db, a, "measured", assignee_id=a.assigned_user_id, note=note, at=now)
    reopened = []
    closed = [a for a in alerts if a.status in ("resolved", "pending_confirmation") and a.resolved_at is not None]
    last = closed[0] if closed else None
    # still RED at the first assessment after closure -> reopen (unless this assessment already raised a new alert)
    if (new_id == -1 and last is not None and last.level == "red" and ra.zone == "red"
            and _first_after(db, subject, last, ra)):
        _reopen(db, last, now)
        reopened.append(last)
    return reopened


def _new_alert_id(db: Session, ra: RiskAssessment) -> int:
    """The alert created by THIS assessment (if any) is not an older alert to check."""
    return db.scalar(select(Alert.id).where(Alert.risk_assessment_id == ra.id)) or -1


def _first_after(db: Session, subject: Pregnancy | Newborn, a: Alert, ra: RiskAssessment) -> bool:
    col = RiskAssessment.pregnancy_id if isinstance(subject, Pregnancy) else RiskAssessment.newborn_id
    other = db.scalar(select(RiskAssessment.id).where(col == subject.id, RiskAssessment.created_at > a.resolved_at,
                                                      RiskAssessment.id != ra.id).limit(1))
    return other is None


def _reopen(db: Session, a: Alert, now: datetime) -> None:
    a.status = "open"
    a.resolved_at = a.confirmed_at = a.measurement_due_at = None
    a.resolved_by_id = a.confirmed_by_id = None
    a.sla_due_at = now + sla_delta(a.level)
    a.reopened_count = (a.reopened_count or 0) + 1
    record_event(db, a, "reopened", assignee_id=a.assigned_user_id, at=now,
                 note="Yopilgandan keyingi birinchi baholash yana qizil zona — ogohlantirish qayta ochildi")
    db.add(AuditLog(user_id=None, action="reopen_alert", entity="alert", entity_id=a.id))


# ---------------- contact attempts / unreachable ----------------
def add_contact_attempt(db: Session, a: Alert, user: User, channel: str, result: str, note: str | None,
                        counselling: list[str], attempted_at: datetime | None) -> list[tuple[str, User | None]]:
    """Log one attempt; may mark the alert "unreachable" (+ escalation). Returns notifications to send."""
    if a.status not in UNRESOLVED or a.status == "pending_confirmation":
        raise LoopError(409, "Faqat yopilmagan ogohlantirish uchun")
    if channel not in CHANNEL_UZ or result not in RESULT_UZ:
        raise LoopError(422, "Aloqa usuli yoki natijasi noto'g'ri")
    now = utcnow()
    at = attempted_at or now
    if at > now + timedelta(minutes=5) or at < a.created_at - timedelta(minutes=5):
        raise LoopError(422, "Urinish vaqti ogohlantirish yaratilgandan keyin va kelajakda bo'lmasligi kerak")
    counselling = [c for c in counselling if c in COUNSELLING_UZ]
    note = (note or "").strip() or None
    if result == "refused":
        if any(c not in counselling for c in REQUIRED_COUNSELLING):
            raise LoopError(422, "Avval maslahat ro'yxatini bajaring: xavfli belgilar tushuntirilishi shart")
        if not note or len(note) < REFUSAL_NOTE_MIN:
            raise LoopError(422, "Xabardor rad etish qaydini yozing (kamida 10 belgi)")
    db.add(ContactAttempt(alert_id=a.id, user_id=user.id, attempted_at=at, channel=channel, result=result,
                          note=note, counselling=counselling or None))
    db.flush()
    record_event(db, a, "contact_attempt", actor_id=user.id, at=now,
                 note=f"{CHANNEL_UZ[channel]}: {RESULT_UZ[result]}")
    notes: list[tuple[str, User | None]] = []
    if result == "refused":
        a.refused_at = a.refused_at or now
        a.retry_due_at = now + timedelta(hours=T.RETRY_HOURS.get(a.level, 24))
    reason = unreachable_reason(db, a)
    if reason and a.unreachable_at is None:
        notes = mark_unreachable(db, a, reason, now)
    return notes


def failed_attempts(attempts: list[ContactAttempt]) -> list[ContactAttempt]:
    return [c for c in attempts if c.result in T.FAILED_CONTACT_RESULTS]


def unreachable_reason(db: Session, a: Alert) -> str | None:
    attempts = list(db.scalars(select(ContactAttempt).where(ContactAttempt.alert_id == a.id)).all())
    if any(c.result == "refused" for c in attempts):
        return "Oila ruxsat bermadi (xabardor rad etish qayd etildi)"
    failed = failed_attempts(attempts)
    days = {c.attempted_at.date() for c in failed}
    if len(failed) >= T.UNREACHABLE_FAILED_ATTEMPTS and len(days) >= T.UNREACHABLE_MIN_DAYS:
        return f"{len(failed)} marta aloqa o'rnatilmadi ({len(days)} xil kunda)"
    return None


def mark_unreachable(db: Session, a: Alert, reason: str, now: datetime) -> list[tuple[str, User | None]]:
    """Still ACTIVE (never silently closed): escalate to the next role with a clear reason + retry schedule."""
    a.unreachable_at, a.unreachable_reason = now, reason[:200]
    a.retry_due_at = a.retry_due_at or now + timedelta(hours=T.RETRY_HOURS.get(a.level, 24))
    record_event(db, a, "unreachable", assignee_id=a.assigned_user_id, at=now, note=reason[:300])
    db.add(AuditLog(user_id=None, action="alert_unreachable", entity="alert", entity_id=a.id))
    notes: list[tuple[str, User | None]] = []
    if a.escalation_level < MAX_ESCALATION_LEVEL:
        notes = escalate(db, a, now, note=f"Bemor bilan aloqa yo'q: {reason}"[:300])
    a.status = "unreachable"
    return notes


def run_followups(db: Session, now: datetime) -> list[tuple[Alert, list[tuple[str, User | None]]]]:
    """Scheduler part of the loop: acknowledged without a measurement in time -> escalate again;
    unreachable / refused alerts re-appear (retry event) every RETRY_HOURS until a measurement arrives."""
    todo = []
    acked = db.scalars(select(Alert).where(Alert.status == "acknowledged", Alert.measurement_due_at.is_not(None),
                                           Alert.measurement_due_at < now)).all()
    for a in acked:
        if find_evidence(db, a) is not None:
            a.measurement_due_at = None  # measured: waiting for the closure, nothing to escalate
            continue
        a.measurement_due_at = None
        if a.escalation_level < MAX_ESCALATION_LEVEL:
            todo.append((a, escalate(db, a, now, note="Qabul qilingan, lekin muddatida yangi o'lchov kiritilmadi")))
        else:
            a.status = "escalated"
            record_event(db, a, "escalated", assignee_id=a.assigned_user_id, at=now,
                         note="Qabul qilingan, lekin muddatida yangi o'lchov kiritilmadi")
    retry = db.scalars(select(Alert).where(Alert.retry_due_at.is_not(None), Alert.retry_due_at < now,
                                           Alert.status.in_(UNRESOLVED))).all()
    for a in retry:
        if find_evidence(db, a) is not None:
            a.retry_due_at = None
            continue
        a.retry_due_at = now + timedelta(hours=T.RETRY_HOURS.get(a.level, 24))
        record_event(db, a, "retry_due", assignee_id=a.assigned_user_id, at=now,
                     note="Qayta urinish vaqti keldi: o'lchov hali kiritilmagan")
    return todo


# ---------------- moved permanently: transfer ----------------
def transfer_patient(db: Session, pat: Patient, target: Mahalla, user: User, ip: str | None) -> int:
    """Responsibility follows the mahalla. Unresolved alerts follow her to the new polyclinic's first assignee.
    Both polyclinics are written to the audit log. Returns the number of alerts moved."""
    from app.services.geo import assign_patient_mahalla

    old_pc = pat.polyclinic_id
    assign_patient_mahalla(db, pat, target)
    db.flush()
    new_pc = target.polyclinic
    moved = 0
    preg_ids = [p.id for p in pat.pregnancies]
    nb_ids = [n.id for p in pat.pregnancies for n in p.newborns]
    stmt = select(Alert).where(Alert.status.in_(UNRESOLVED))
    alerts = [a for a in db.scalars(stmt).all() if a.pregnancy_id in preg_ids or a.newborn_id in nb_ids]
    for a in alerts:
        first = first_assignee(db, new_pc.id, new_pc.district_id, a.level)
        a.assigned_user_id = first.id if first else None
        record_event(db, a, "transferred", assignee_id=a.assigned_user_id, actor_id=user.id,
                     note=f"Bemor boshqa mahallaga ko'chdi: {target.name} ({new_pc.code})")
        moved += 1
    details = f"from_polyclinic_id={old_pc},to_polyclinic_id={new_pc.id}"
    for action in ("transfer_out", "transfer_in"):
        db.add(AuditLog(user_id=user.id, action=action, entity="patient", entity_id=pat.id,
                        from_polyclinic_id=old_pc, to_polyclinic_id=new_pc.id, details=details, ip=ip))
    return moved
