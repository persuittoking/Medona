"""Polyclinic dashboard (staff, tenant-scoped), model analytics and the admin audit log."""
import json
import statistics
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.api.deps import current_user, require_admin
from app.api.tenancy import Tenant, staff
from app.config import BACKEND_DIR
from app.db import get_db
from app.models import Alert, AuditLog, Patient, Polyclinic, Pregnancy, RiskAssessment, User, utcnow
from app.risk.features import gest_weeks
from app.security.crypto import decrypt, mask_name

router = APIRouter(prefix="/api", tags=["dashboard"])


def _pregnancies(t: Tenant) -> list[tuple[Pregnancy, Patient]]:
    stmt = select(Pregnancy, Patient).join(Patient, Pregnancy.patient_id == Patient.id).where(Pregnancy.status == "active")
    return list(t.db.execute(t.patients(stmt)).all())


def _alerts(t: Tenant) -> list[Alert]:
    stmt = select(Alert).join(Pregnancy, Alert.pregnancy_id == Pregnancy.id).join(Patient, Pregnancy.patient_id == Patient.id)
    return list(t.db.scalars(t.patients(stmt)).all())


def zone_kpis(pregs: list[Pregnancy], alerts: list[Alert]) -> dict:
    """Shared by the staff dashboard and the admin aggregates (counts only)."""
    now = utcnow()
    active = [a for a in alerts if a.status in ("open", "escalated")]
    breaches = [a for a in alerts if (a.status in ("open", "escalated") and a.sla_due_at < now) or a.escalation_level > 0
                or (a.acknowledged_at and a.acknowledged_at > a.sla_due_at)]
    ack = [(a.acknowledged_at - a.created_at).total_seconds() / 60 for a in alerts if a.acknowledged_at]
    return {
        "active_pregnancies": len(pregs),
        **{z: sum(1 for p in pregs if p.current_zone == z) for z in ("red", "yellow", "green")},
        "open_alerts": len(active),
        "open_red_alerts": sum(1 for a in active if a.level == "red"),
        "sla_breaches": len(breaches),
        "median_ack_minutes": round(statistics.median(ack), 1) if ack else None,
    }


@router.get("/dashboard/summary")
def summary(t: Tenant = Depends(staff())) -> dict:
    return {**zone_kpis([p for p, _ in _pregnancies(t)], _alerts(t)), "synthetic": True}


@router.get("/dashboard/trend")
def trend(weeks: int = 12, t: Tenant = Depends(staff())) -> list[dict]:
    start = date.today() - timedelta(weeks=weeks)
    stmt = (select(RiskAssessment.created_at, RiskAssessment.zone, RiskAssessment.pregnancy_id)
            .join(Pregnancy, RiskAssessment.pregnancy_id == Pregnancy.id).join(Patient, Pregnancy.patient_id == Patient.id)
            .where(RiskAssessment.created_at >= start, RiskAssessment.zone != "green"))
    buckets: dict[int, dict[str, set]] = {i: {"red": set(), "yellow": set()} for i in range(weeks + 1)}
    for created, zone, pid in t.db.execute(t.patients(stmt)).all():
        buckets[min(weeks, (created.date() - start).days // 7)][zone].add(pid)
    return [{"week_start": str(start + timedelta(weeks=i)), "red": len(b["red"]), "yellow": len(b["yellow"])}
            for i, b in buckets.items()]


@router.get("/dashboard/top")
def top(limit: int = 10, t: Tenant = Depends(staff())) -> list[dict]:
    order = {"red": 0, "yellow": 1, "green": 2}
    pregs = sorted(_pregnancies(t), key=lambda x: (order[x[0].current_zone], -(x[0].current_risk_score or 0)))[:limit]
    out = []
    for p, pat in pregs:
        ra = t.db.scalars(select(RiskAssessment).where(RiskAssessment.pregnancy_id == p.id)
                          .order_by(RiskAssessment.id.desc())).first()
        hits = [h for h in (ra.rule_hits + ra.trend_hits) if h["zone"] != "factor"] if ra else []
        out.append({"patient_id": pat.id, "pregnancy_id": p.id, "code": pat.code,
                    "name_masked": mask_name(decrypt(pat.full_name_enc)), "mahalla_name": pat.mahalla.name,
                    "gestational_weeks": gest_weeks(p.lmp_date, date.today()), "zone": p.current_zone,
                    "risk": p.current_risk_score,
                    "main_reason": hits[0]["uz_text"] if hits else (ra.shap_top[0]["uz_label"] if ra and ra.shap_top else None)})
    return out


@router.get("/analytics/model")
def model_metrics(_: User = Depends(current_user)) -> dict:
    path = BACKEND_DIR / "ml" / "artifacts" / "metrics.json"
    if not path.exists():
        raise HTTPException(404, "Model hali o'qitilmagan (ml/train.py)")
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/audit")
def audit_log(action: str | None = None, entity: str | None = None, limit: int = 200,
              user: User = Depends(require_admin), db=Depends(get_db)) -> list[dict]:
    """Admin audit log: who did what. Entity ids only — no patient names."""
    stmt = select(AuditLog, User, Polyclinic).outerjoin(User, AuditLog.user_id == User.id) \
        .outerjoin(Polyclinic, User.polyclinic_id == Polyclinic.id)
    if user.role == "district_admin":
        stmt = stmt.where(User.district_id == user.district_id)
    else:
        stmt = stmt.where(User.region_id == user.region_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if entity:
        stmt = stmt.where(AuditLog.entity == entity)
    rows = db.execute(stmt.order_by(AuditLog.id.desc()).limit(min(limit, 1000))).all()
    return [{"id": a.id, "created_at": a.created_at, "action": a.action, "entity": a.entity, "entity_id": a.entity_id,
             "ip": a.ip, "user": u.username if u else "tizim", "role": u.role if u else None,
             "polyclinic": pc.code if pc else None} for a, u, pc in rows]
