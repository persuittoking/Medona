"""Adaptive visit intensity (advisory only; the mandatory 12 antenatal visits are NEVER reduced).

Rules:
- National standard: `T.STANDARD_VISITS = 12` mandatory antenatal visits (`T.STANDARD_VISIT_WEEKS`).
  Total scheduled visits is ALWAYS 12 — never fewer.
- Each scheduled visit has an intensity: `"To'liq"` (full doctor visit) or `"Yengil"` (nurse-led light visit,
  standard checks only).
- Eligible for `"Yengil"`:
  1. Last `T.CONSECUTIVE_GREEN_REQUIRED` (3) consecutive assessments are `"green"`,
  2. No Tier B (or Tier A / red) risk factor on the latest assessment or pregnancy record,
  3. No trend hit on the latest assessment,
  4. No open/escalated alert,
  5. Not in the final weeks (`gestational_weeks < light_visit_max_weeks`, default 36; from 36 weeks all visits
     stay `"To'liq"`).
- Any yellow/red result or new risk factor immediately returns ALL remaining visits to `"To'liq"`.
- Only the `doctor` role can confirm `"Yengil"` intensity; it is never automatic. Every recommendation and
  confirmation is written to `AuditLog`.
"""
from __future__ import annotations

from datetime import date

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Alert, AuditLog, Pregnancy, RiskAssessment, User, utcnow
from app.risk import thresholds as T
from app.risk.features import gest_weeks
from app.risk.rules import red_rules, yellow_rules
from app.services.alerts import ACTIVE
from app.services.scoring import preg_dict, visit_dict

FULL_UZ = "To'liq"
LIGHT_UZ = "Yengil"


def _static_risk_hits(preg_data: dict, visits: list[dict]) -> list[dict]:
    if not visits:
        return []
    last = visits[-1]
    prev = visits[-2] if len(visits) >= 2 else None
    return red_rules(preg_data, last) + yellow_rules(preg_data, last, prev)


def evaluate_eligibility(
    preg_data: dict,
    visits: list[dict],
    assessments: list[dict],
    *,
    has_open_alert: bool = False,
    current_weeks: float | None = None,
    max_weeks: float | None = None,
    required_green: int | None = None,
    confirmed: bool = False,
) -> dict:
    """Pure eligibility and 12-visit schedule calculator (never recommends fewer than 12 visits)."""
    s = get_settings()
    max_w = float(max_weeks if max_weeks is not None else s.light_visit_max_weeks)
    req_green = int(required_green if required_green is not None else T.CONSECUTIVE_GREEN_REQUIRED)
    if current_weeks is None:
        current_weeks = visits[-1]["gestational_weeks"] if visits else gest_weeks(preg_data["lmp_date"], date.today())

    consecutive_green = 0
    for ra in reversed(assessments):
        if ra.get("zone") == "green":
            consecutive_green += 1
        else:
            break

    last_ra = assessments[-1] if assessments else None
    last_zone = last_ra.get("zone") if last_ra else "green"
    ra_rule_hits = list(last_ra.get("rule_hits") or []) if last_ra else []
    ra_trend_hits = list(last_ra.get("trend_hits") or []) if last_ra else []
    live_hits = _static_risk_hits(preg_data, visits)

    has_tier_b = any(h.get("code") in T.TIER_B_RULES or h.get("zone") == "factor" for h in ra_rule_hits + live_hits)
    has_any_rule = bool(ra_rule_hits or live_hits)
    has_trend = bool(ra_trend_hits)
    in_final_weeks = current_weeks >= max_w

    n_completed = min(len(visits), T.STANDARD_VISITS)
    raw_slots = []
    for idx, target_w in enumerate(T.STANDARD_VISIT_WEEKS, start=1):
        status = "completed" if idx <= n_completed else "upcoming"
        can_be_light = status == "upcoming" and target_w < max_w and target_w >= current_weeks
        raw_slots.append({"visit_number": idx, "target_week": target_w, "status": status, "can_be_light": can_be_light})

    any_light_slot = any(sl["can_be_light"] for sl in raw_slots)
    eligible = (
        last_zone == "green"
        and consecutive_green >= req_green
        and not has_tier_b
        and not has_any_rule
        and not has_trend
        and not has_open_alert
        and not in_final_weeks
        and any_light_slot
    )

    active_confirmed = bool(confirmed and eligible)
    schedule = []
    recommended_light = 0
    confirmed_light = 0
    for sl in raw_slots:
        rec = LIGHT_UZ if (eligible and sl["can_be_light"]) else FULL_UZ
        act = LIGHT_UZ if (active_confirmed and sl["can_be_light"]) else FULL_UZ
        if rec == LIGHT_UZ:
            recommended_light += 1
        if act == LIGHT_UZ:
            confirmed_light += 1
        schedule.append({
            "visit_number": sl["visit_number"],
            "target_week": sl["target_week"],
            "status": sl["status"],
            "recommended_intensity": rec,
            "intensity": act,
            "intensity_code": "light" if act == LIGHT_UZ else "full",
        })

    assert len(schedule) == T.STANDARD_VISITS == 12, "Mandatory 12 visits must never be reduced"

    if eligible:
        recommendation_uz = f"Tavsiya: yengil ko'rik (oxirgi {consecutive_green} ta natija yashil)"
        reason_uz = (
            f"Oxirgi {consecutive_green} ta ketma-ket ko'rik yashil zonada, xavf omillari (Tier B), "
            f"yomonlashish trendi va ochiq ogohlantirishlar yo'q, muddat {int(max_w)} haftadan kichik. "
            f"Majburiy {T.STANDARD_VISITS} ta tashrif soni qisqartirilmaydi ({int(max_w)} haftadan boshlab barcha ko'riklar {FULL_UZ})."
        )
    else:
        recommendation_uz = None
        if last_zone in ("yellow", "red"):
            reason_uz = f"Joriy zona {last_zone.upper()} — barcha qolgan ko'riklar {FULL_UZ} (shifokor ko'rigi)."
        elif has_tier_b or has_any_rule:
            reason_uz = f"Xavf omili mavjud — barcha qolgan ko'riklar {FULL_UZ} (shifokor ko'rigi)."
        elif has_trend:
            reason_uz = f"O'zgarish trendi qayd etilgan — barcha qolgan ko'riklar {FULL_UZ} (shifokor ko'rigi)."
        elif has_open_alert:
            reason_uz = f"Ochiq ogohlantirish mavjud — barcha qolgan ko'riklar {FULL_UZ} (shifokor ko'rigi)."
        elif in_final_weeks or not any_light_slot:
            reason_uz = f"{int(max_w)} haftadan boshlab barcha ko'riklar {FULL_UZ} (shifokor ko'rigi) bo'lib qoladi."
        else:
            reason_uz = (
                f"Yengil ko'rik tavsiyasi uchun kamida {req_green} ta ketma-ket yashil natija kerak "
                f"(hozir: {consecutive_green} ta) — barcha ko'riklar {FULL_UZ}."
            )

    return {
        "standard_visits": T.STANDARD_VISITS,
        "total_scheduled_visits": len(schedule),
        "eligible": eligible,
        "confirmed": active_confirmed,
        "consecutive_green": consecutive_green,
        "consecutive_green_required": req_green,
        "light_visit_max_weeks": max_w,
        "recommendation_uz": recommendation_uz,
        "reason_uz": reason_uz,
        "recommended_light_visits": recommended_light,
        "confirmed_light_visits": confirmed_light,
        "schedule": schedule,
    }


def pregnancy_visit_plan(db: Session, preg: Pregnancy, *, log_recommendation: bool = False,
                         actor_id: int | None = None, today: date | None = None) -> dict:
    """Compute the 12-visit plan for a Pregnancy row and keep confirmation state consistent."""
    today = today or date.today()
    assessments = db.scalars(
        select(RiskAssessment).where(RiskAssessment.pregnancy_id == preg.id).order_by(RiskAssessment.id)
    ).all()
    open_alert = db.scalars(
        select(Alert.id).where(Alert.pregnancy_id == preg.id, Alert.status.in_(ACTIVE)).limit(1)
    ).first() is not None
    visits = [visit_dict(v) for v in preg.visits]
    ra_dicts = [{"zone": a.zone, "rule_hits": a.rule_hits, "trend_hits": a.trend_hits} for a in assessments]
    gw = gest_weeks(preg.lmp_date, today)

    res = evaluate_eligibility(
        preg_dict(preg),
        visits,
        ra_dicts,
        has_open_alert=open_alert,
        current_weeks=gw,
        confirmed=bool(preg.light_visit_confirmed),
    )

    if not res["eligible"] and preg.light_visit_confirmed:
        preg.light_visit_confirmed = False
        preg.light_visit_confirmed_by = None
        preg.light_visit_confirmed_at = None
        preg.confirmed_light_visits_count = 0
        db.add(AuditLog(user_id=actor_id, action="reset_visit_intensity", entity="pregnancy", entity_id=preg.id,
                        details="returned_all_to_full"))
    elif res["confirmed"]:
        preg.confirmed_light_visits_count = res["confirmed_light_visits"]

    if log_recommendation and res["eligible"]:
        existing = db.scalars(
            select(AuditLog.id).where(
                AuditLog.action == "recommend_light_visit",
                AuditLog.entity == "pregnancy",
                AuditLog.entity_id == preg.id,
            ).limit(1)
        ).first()
        if existing is None:
            db.add(AuditLog(
                user_id=actor_id,
                action="recommend_light_visit",
                entity="pregnancy",
                entity_id=preg.id,
                details=f"consecutive_green={res['consecutive_green']}",
            ))

    conf_user = db.get(User, preg.light_visit_confirmed_by) if preg.light_visit_confirmed_by else None
    res["confirmed_by"] = conf_user.full_name if (res["confirmed"] and conf_user) else None
    res["confirmed_at"] = preg.light_visit_confirmed_at if res["confirmed"] else None
    return res


def sync_after_visit(db: Session, preg: Pregnancy, ra: RiskAssessment, actor_id: int | None = None) -> dict:
    """Called right after a visit assessment is stored: resets on yellow/red/risk factor or logs recommendation."""
    if ra.zone != "green" or ra.rule_hits or ra.trend_hits:
        if preg.light_visit_confirmed:
            preg.light_visit_confirmed = False
            preg.light_visit_confirmed_by = None
            preg.light_visit_confirmed_at = None
            preg.confirmed_light_visits_count = 0
            db.add(AuditLog(user_id=actor_id, action="reset_visit_intensity", entity="pregnancy", entity_id=preg.id,
                            details=f"zone={ra.zone}"))
    plan = pregnancy_visit_plan(db, preg, log_recommendation=False, actor_id=actor_id)
    if plan["eligible"]:
        db.add(AuditLog(
            user_id=actor_id,
            action="recommend_light_visit",
            entity="pregnancy",
            entity_id=preg.id,
            details=f"consecutive_green={plan['consecutive_green']}",
        ))
    return plan


def confirm_light_visit_plan(db: Session, preg: Pregnancy, doctor: User, ip: str | None = None) -> dict:
    """Doctor-only confirmation of the recommended 'Yengil' visit intensity."""
    if doctor.role != "doctor":
        raise HTTPException(403, "Faqat shifokor tasdiqlashi mumkin")
    if preg.status != "active":
        raise HTTPException(409, "Bu homiladorlik faol emas")
    plan = pregnancy_visit_plan(db, preg, log_recommendation=True, actor_id=doctor.id)
    if not plan["eligible"]:
        raise HTTPException(409, "Bemor yengil ko'rik tavsiyasiga mos emas")
    preg.light_visit_confirmed = True
    preg.light_visit_confirmed_by = doctor.id
    preg.light_visit_confirmed_at = utcnow()
    preg.confirmed_light_visits_count = plan["recommended_light_visits"]
    db.add(AuditLog(
        user_id=doctor.id,
        action="confirm_light_visit",
        entity="pregnancy",
        entity_id=preg.id,
        details=f"confirmed_light_visits={preg.confirmed_light_visits_count}",
        ip=ip,
    ))
    db.flush()
    return pregnancy_visit_plan(db, preg, actor_id=doctor.id)
