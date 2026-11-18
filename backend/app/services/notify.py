"""Telegram notifications for alerts (send-only adapter; the interactive aiogram bot is a later phase).

Privacy: messages carry ONLY the pseudonymous patient code, gestational week, zone and the 3 de-identified doctor
bullets — never name, JShShIR, phone, address or mahalla. District admins get a count only (no patient code).
Demo never fails: without TELEGRAM_BOT_TOKEN or a linked telegram_chat_id, or on any network error, the message
goes to the in-process OUTBOX + the log ("offline"). Nothing here ever raises.
"""
from __future__ import annotations

import json
import logging
import urllib.request
from collections import deque
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Alert, AuditLog, Patient, Pregnancy, User, utcnow
from app.risk.engine import ZONE_UZ
from app.risk.features import gest_weeks

log = logging.getLogger("onaradar.notify")

TELEGRAM_TIMEOUT_S = 5.0
OUTBOX: deque[dict] = deque(maxlen=200)  # last messages (sent or offline), for tests and the demo
FINAL_DECISION_UZ = "Yakuniy qaror shifokorga tegishli."
LEVEL_ICON = {"red": "🔴", "yellow": "🟡"}


def _send_telegram(chat_id: str, text: str) -> bool:
    token = get_settings().telegram_bot_token
    if not token or not chat_id:
        return False
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                                 data=json.dumps({"chat_id": chat_id, "text": text}).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TELEGRAM_TIMEOUT_S) as r:  # noqa: S310 - fixed https host
            return 200 <= r.status < 300
    except Exception as e:  # noqa: BLE001 - offline fallback, never raise
        log.warning("Telegram send failed: %s", type(e).__name__)
        return False


def notify_user(db: Session, user: User | None, text: str, alert_id: int | None, kind: str) -> str:
    """Send `text` to `user`; returns "sent" or "offline". Writes an audit row (no message text in the audit)."""
    if user is None:
        return "offline"
    ok = _send_telegram(user.telegram_chat_id or "", text)
    status = "sent" if ok else "offline"
    OUTBOX.append({"at": utcnow(), "user_id": user.id, "role": user.role, "alert_id": alert_id, "kind": kind,
                   "status": status, "text": text})
    if not ok:
        log.info("telegram (offline) -> %s #%s [%s]", user.role, user.id, kind)
    db.add(AuditLog(user_id=None, action=f"telegram_{kind}", entity="alert", entity_id=alert_id))
    return status


def _bullets(db: Session, alert: Alert) -> list[str]:
    from app.services.ai_summary import alert_summary  # lazy: ai_summary -> scoring -> alerts

    s = alert_summary(db, alert.risk_assessment_id)
    if s["summary_bullets"]:
        return list(s["summary_bullets"])
    ra = alert.risk_assessment
    return [h["uz_text"] for h in (ra.rule_hits + ra.trend_hits) if h["zone"] != "factor"][:3] if ra else []


def _minutes_left(due: datetime) -> int:
    return max(0, round((due - utcnow()).total_seconds() / 60))


def alert_text(db: Session, alert: Alert, headline: str) -> str:
    preg = alert.pregnancy
    code = preg.patient.code if preg else "—"
    gw = gest_weeks(preg.lmp_date, alert.created_at.date()) if preg else None
    lines = [f"{LEVEL_ICON.get(alert.level, '')} {headline}",
             f"Bemor kodi: {code}" + (f" · {gw:g} hafta" if gw is not None else ""),
             f"Zona: {ZONE_UZ.get(alert.level, alert.level)}"]
    lines += [f"• {b}" for b in _bullets(db, alert)]
    lines.append(f"Javob berish uchun qoldi: {_minutes_left(alert.sla_due_at)} daqiqa")
    lines += [FINAL_DECISION_UZ, "Sintetik ma'lumot (demo)"]
    return "\n".join(lines)


def notify_new_alert(db: Session, alert: Alert) -> str:
    assignee = db.get(User, alert.assigned_user_id) if alert.assigned_user_id else None
    return notify_user(db, assignee, alert_text(db, alert, "Yangi ogohlantirish"), alert.id, "new_alert")


def notify_escalated(db: Session, alert: Alert, assignee: User | None) -> str:
    head = f"ESKALATSIYA ({alert.escalation_level}-daraja): javob muddati o'tdi, siz mas'ul etib belgilandingiz"
    return notify_user(db, assignee, alert_text(db, alert, head), alert.id, "escalated")


def notify_reassigned(db: Session, alert: Alert, assignee: User | None) -> str:
    return notify_user(db, assignee, alert_text(db, alert, "Ogohlantirish sizga qayta biriktirildi"), alert.id,
                       "reassigned")


def notify_admin_count(db: Session, alert: Alert, admin: User | None) -> str:
    """District admin: aggregate count only — no patient code, no clinical details."""
    pc_id = alert.pregnancy.patient.polyclinic_id
    open_red = db.scalar(select(func.count()).select_from(Alert)
                         .join(Pregnancy, Alert.pregnancy_id == Pregnancy.id)
                         .join(Patient, Pregnancy.patient_id == Patient.id)
                         .where(Patient.polyclinic_id == pc_id, Alert.level == "red",
                                Alert.status.in_(("open", "escalated")), Alert.escalation_level >= 2)) or 0
    text = (f"⚠️ {alert.pregnancy.patient.polyclinic.code}: {ZONE_UZ.get(alert.level, alert.level)} ogohlantirish "
            f"belgilangan muddatda qabul qilinmadi ({alert.escalation_level}-daraja eskalatsiya). "
            f"Poliklinikada hozir shunday ogohlantirishlar soni: {open_red} ta. Bemor ma'lumotlari yuborilmaydi.")
    return notify_user(db, admin, text, alert.id, "admin_count")


def notify_new_alert_job(alert_id: int) -> None:
    """Background task after a visit save (runs after the AI summary task, so the bullets are usually ready)."""
    from app.db import SessionLocal

    try:
        with SessionLocal() as db:
            alert = db.get(Alert, alert_id)
            if alert is not None and alert.status in ("open", "escalated"):
                notify_new_alert(db, alert)
                db.commit()
    except Exception:
        log.exception("new-alert notification failed for alert %s", alert_id)
