"""Plausibility signals (task 12, part E): simple statistics per user over the last QUALITY_WINDOW_DAYS days.

These are SIGNALS for the department head, never accusations ("signal, ayblov emas"):
- identical_bp   the user's single most common BP pair covers a large share of her visits
- digit_bias     most BP values end in 0 or 5 (terminal-digit preference)
- low_variation  systolic values barely vary across different patients
- fast_entry     visit form opened -> saved in under QUALITY_FAST_ENTRY_S seconds (client sends opened_at)
- burst          many visits saved by one user within the same minute
fast_entry / burst only use visits entered through the app form (opened_at present), not imported history.
"""
from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from datetime import date, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Alert, Patient, Pregnancy, QualityFlag, User, Visit, utcnow
from app.risk import thresholds as T

REASON_UZ = {
    "identical_bp": "Bir xil arterial bosim qiymatlari ko'p",
    "digit_bias": "Qiymatlar asosan 0 yoki 5 bilan tugaydi",
    "low_variation": "Sistolik bosim deyarli o'zgarmaydi",
    "fast_entry": "Shakl juda tez to'ldirilgan",
    "burst": "Bir daqiqada bir nechta tashrif saqlangan",
}
SIGNAL_LABEL_UZ = "signal, ayblov emas"


def _visits(db: Session, polyclinic_id: int, since: date) -> list[tuple[Visit, User]]:
    stmt = (select(Visit, User).join(User, Visit.entered_by == User.id)
            .where(User.polyclinic_id == polyclinic_id, Visit.visit_date >= since))
    return list(db.execute(stmt).all())


def compute_flags(db: Session, polyclinic_id: int, today: date | None = None) -> list[QualityFlag]:
    """Recompute and STORE the flags of one polyclinic (replaces the previous set)."""
    today = today or date.today()
    rows = _visits(db, polyclinic_id, today - timedelta(days=T.QUALITY_WINDOW_DAYS))
    by_user: dict[int, list[Visit]] = defaultdict(list)
    for v, u in rows:
        by_user[u.id].append(v)
    flags: list[QualityFlag] = []

    def add(uid: int, reason: str, value: float | None, visit_id: int | None = None) -> None:
        flags.append(QualityFlag(polyclinic_id=polyclinic_id, user_id=uid, visit_id=visit_id, reason=reason,
                                 value=None if value is None else round(value, 3)))

    for uid, visits in by_user.items():
        bp = [v for v in visits if v.systolic is not None and v.diastolic is not None]
        if len(bp) >= T.QUALITY_MIN_VISITS:
            pairs = Counter((v.systolic, v.diastolic) for v in bp)
            top, n_top = pairs.most_common(1)[0]
            share = n_top / len(bp)
            if share >= T.QUALITY_IDENTICAL_BP_SHARE:
                add(uid, "identical_bp", share)
                for v in bp:
                    if (v.systolic, v.diastolic) == top:
                        add(uid, "identical_bp", None, v.id)
            values = [x for v in bp for x in (v.systolic, v.diastolic)]
            digit = sum(1 for x in values if x % 5 == 0) / len(values)
            if digit >= T.QUALITY_DIGIT_BIAS_SHARE:
                add(uid, "digit_bias", digit)
            sd = statistics.pstdev([v.systolic for v in bp])
            if sd < T.QUALITY_LOW_SYS_SD:
                add(uid, "low_variation", sd)
        entered = [v for v in visits if v.opened_at is not None and v.created_at is not None]
        for v in entered:
            secs = (v.created_at - v.opened_at).total_seconds()
            if 0 <= secs < T.QUALITY_FAST_ENTRY_S:
                add(uid, "fast_entry", secs, v.id)
        minutes: dict = defaultdict(list)
        for v in entered:
            minutes[v.created_at.replace(second=0, microsecond=0)].append(v)
        for group in minutes.values():
            if len(group) >= T.QUALITY_BURST_PER_MINUTE:
                for v in group:
                    add(uid, "burst", len(group), v.id)

    db.execute(delete(QualityFlag).where(QualityFlag.polyclinic_id == polyclinic_id))
    db.add_all(flags)
    db.flush()
    return flags


def quality_report(db: Session, polyclinic_id: int) -> list[dict]:
    """Per user: counts per reason + the patient CODES of flagged visits (no names). Department head only."""
    flags = compute_flags(db, polyclinic_id)
    users = {u.id: u for u in db.scalars(select(User).where(User.polyclinic_id == polyclinic_id)).all()}
    visit_ids = {f.visit_id for f in flags if f.visit_id}
    codes = dict(db.execute(select(Visit.id, Patient.code).join(Pregnancy, Visit.pregnancy_id == Pregnancy.id)
                            .join(Patient, Pregnancy.patient_id == Patient.id)
                            .where(Visit.id.in_(visit_ids))).all()) if visit_ids else {}
    out: dict[int, dict] = {}
    for f in flags:
        u = users.get(f.user_id)
        row = out.setdefault(f.user_id, {"user_id": f.user_id, "user": u.full_name if u else "—",
                                         "role": u.role if u else None, "signals": {}})
        sig = row["signals"].setdefault(f.reason, {"reason": f.reason, "label_uz": REASON_UZ[f.reason],
                                                   "value": None, "visits": 0, "patient_codes": []})
        if f.visit_id is None:
            sig["value"] = f.value
        else:
            sig["visits"] += 1
            code = codes.get(f.visit_id)
            if code and code not in sig["patient_codes"]:
                sig["patient_codes"].append(code)
    return [{**r, "signals": list(r["signals"].values())} for r in out.values()]


def unreachable_red_alerts(db: Session, polyclinic_id: int) -> list[Alert]:
    """Unresolved RED alerts whose patient could not be reached (and no measurement since). Any age."""
    from app.services.alerts import UNRESOLVED, polyclinic_alerts
    from app.services.closed_loop import find_evidence

    rows = db.scalars(polyclinic_alerts(select(Alert), polyclinic_id)
                      .where(Alert.level == "red", Alert.status.in_(UNRESOLVED),
                             Alert.unreachable_at.is_not(None))).unique().all()
    return [a for a in rows if find_evidence(db, a) is None]


def loop_tiles(db: Session, polyclinic_id: int) -> dict:
    """Department head tiles: acknowledged-but-unmeasured rate and unreachable RED count (last 30 days)."""
    from app.services.alerts import UNRESOLVED, polyclinic_alerts
    from app.services.closed_loop import find_evidence

    since = utcnow() - timedelta(days=T.QUALITY_WINDOW_DAYS)
    alerts = list(db.scalars(polyclinic_alerts(select(Alert), polyclinic_id)
                             .where(Alert.created_at >= since)).unique().all())
    acked = [a for a in alerts if a.acknowledged_at is not None]
    no_measure = [a for a in acked if a.status in UNRESOLVED and find_evidence(db, a) is None]
    unreachable_red = unreachable_red_alerts(db, polyclinic_id)
    return {
        "acknowledged": len(acked),
        "acknowledged_without_measurement": len(no_measure),
        "acknowledged_without_measurement_rate": round(len(no_measure) / len(acked), 3) if acked else 0.0,
        "unreachable_red": len(unreachable_red),
        "window_days": T.QUALITY_WINDOW_DAYS,
    }
