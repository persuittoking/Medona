"""Polyclinic dashboard (staff, tenant-scoped), model analytics and the admin audit log."""
import json
import statistics
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from app.api.deps import current_user, require_admin
from app.api.tenancy import Tenant, staff
from app.config import BACKEND_DIR, get_settings
from app.db import get_db
from app.models import (
    ADMIN_ROLES,
    Alert,
    AuditLog,
    Newborn,
    Patient,
    Polyclinic,
    Pregnancy,
    RiskAssessment,
    User,
    utcnow,
)
from app.risk.features import gest_weeks
from app.risk.infant import age_days
from app.security.crypto import decrypt, mask_name
from app.services.alerts import ESCALATION_CHAIN, by_subject

router = APIRouter(prefix="/api", tags=["dashboard"])


SubjectQ = Query("pregnancy", pattern="^(pregnancy|child|all)$")


def _pregnancies(t: Tenant) -> list[tuple[Pregnancy, Patient]]:
    stmt = select(Pregnancy, Patient).join(Patient, Pregnancy.patient_id == Patient.id).where(Pregnancy.status == "active")
    return list(t.db.execute(t.patients(stmt)).all())


def _children(t: Tenant) -> list[Newborn]:
    return list(t.db.scalars(t.children(select(Newborn).where(Newborn.status == "active"))).all())


def _alerts(t: Tenant, subject: str = "all") -> list[Alert]:
    return list(t.db.scalars(by_subject(t.alerts(select(Alert)), subject)).unique().all())


def zone_kpis(subjects: list, alerts: list[Alert]) -> dict:
    """Shared by the staff dashboard and the admin aggregates (counts only). `subjects`: anything with current_zone."""
    now = utcnow()
    active = [a for a in alerts if a.status in ("open", "escalated")]
    breaches = [a for a in alerts if (a.status in ("open", "escalated") and a.sla_due_at < now) or a.escalation_level > 0
                or (a.acknowledged_at and a.acknowledged_at > a.sla_due_at)]
    ack = [(a.acknowledged_at - a.created_at).total_seconds() / 60 for a in alerts if a.acknowledged_at]
    return {
        "active": len(subjects),
        **{z: sum(1 for p in subjects if p.current_zone == z) for z in ("red", "yellow", "green")},
        "open_alerts": len(active),
        "open_red_alerts": sum(1 for a in active if a.level == "red"),
        "sla_breaches": len(breaches),
        "median_ack_minutes": round(statistics.median(ack), 1) if ack else None,
    }


@router.get("/dashboard/summary")
def summary(subject: str = SubjectQ, t: Tenant = Depends(staff())) -> dict:
    """KPIs for the chosen subject (pregnancy | child | all) + the counts shown on the switch segments."""
    pregs = [p for p, _ in _pregnancies(t)]
    kids = _children(t)
    chosen = (pregs if subject != "child" else []) + (kids if subject != "pregnancy" else [])
    return {**zone_kpis(chosen, _alerts(t, subject)), "subject": subject,
            "active_pregnancies": len(pregs), "active_children": len(kids),
            "counts": {"pregnancy": len(pregs), "child": len(kids), "all": len(pregs) + len(kids)}, "synthetic": True}


@router.get("/dashboard/trend")
def trend(weeks: int = 12, subject: str = SubjectQ, t: Tenant = Depends(staff())) -> list[dict]:
    start = date.today() - timedelta(weeks=weeks)
    buckets: dict[int, dict[str, set]] = {i: {"red": set(), "yellow": set()} for i in range(weeks + 1)}
    rows = []
    if subject != "child":
        stmt = (select(RiskAssessment.created_at, RiskAssessment.zone, RiskAssessment.pregnancy_id)
                .join(Pregnancy, RiskAssessment.pregnancy_id == Pregnancy.id).join(Patient, Pregnancy.patient_id == Patient.id)
                .where(RiskAssessment.created_at >= start, RiskAssessment.zone != "green"))
        rows += [(c, z, ("p", i)) for c, z, i in t.db.execute(t.patients(stmt)).all()]
    if subject != "pregnancy":
        stmt = (select(RiskAssessment.created_at, RiskAssessment.zone, RiskAssessment.newborn_id)
                .join(Newborn, RiskAssessment.newborn_id == Newborn.id)
                .where(RiskAssessment.created_at >= start, RiskAssessment.zone != "green"))
        rows += [(c, z, ("c", i)) for c, z, i in t.db.execute(t.children(stmt)).all()]
    for created, zone, key in rows:
        buckets[min(weeks, (created.date() - start).days // 7)][zone].add(key)
    return [{"week_start": str(start + timedelta(weeks=i)), "red": len(b["red"]), "yellow": len(b["yellow"])}
            for i, b in buckets.items()]


def _top_pregnancies(t: Tenant) -> list[dict]:
    out = []
    for p, pat in _pregnancies(t):
        out.append({"subject": "pregnancy", "patient_id": pat.id, "pregnancy_id": p.id, "newborn_id": None,
                    "code": pat.code, "_pat": pat, "_obj": p, "zone": p.current_zone, "risk": p.current_risk_score})
    return out


@router.get("/dashboard/top")
def top(limit: int = 10, subject: str = SubjectQ, t: Tenant = Depends(staff())) -> list[dict]:
    """Highest-risk subjects: zone first, then the ML probability (children: rule severity, never shown as %)."""
    order = {"red": 0, "yellow": 1, "green": 2}
    rows = _top_pregnancies(t) if subject != "child" else []
    if subject != "pregnancy":
        rows += [{"subject": "child", "patient_id": nb.pregnancy.patient_id, "pregnancy_id": None, "newborn_id": nb.id,
                  "code": nb.code, "_obj": nb, "zone": nb.current_zone, "risk": nb.current_risk_score} for nb in _children(t)]
    rows = sorted(rows, key=lambda r: (order[r["zone"]], -(r["risk"] or 0)))[:limit]
    out = []
    today = date.today()
    for r in rows:
        obj = r.pop("_obj")
        if r["subject"] == "pregnancy":
            pat = r.pop("_pat")
            ra = t.db.scalars(select(RiskAssessment).where(RiskAssessment.pregnancy_id == obj.id)
                              .order_by(RiskAssessment.id.desc())).first()
            r.update(name_masked=mask_name(decrypt(pat.full_name_enc)), mahalla_name=pat.mahalla.name,
                     gestational_weeks=gest_weeks(obj.lmp_date, today), child_age_days=None)
        else:
            ra = t.db.scalars(select(RiskAssessment).where(RiskAssessment.newborn_id == obj.id)
                              .order_by(RiskAssessment.id.desc())).first()
            r.update(name_masked=None, mahalla_name=obj.pregnancy.patient.mahalla.name, gestational_weeks=None,
                     child_age_days=age_days(obj.birth_date, today), risk=None)
        hits = [h for h in (ra.rule_hits + ra.trend_hits) if h["zone"] != "factor"] if ra else []
        r["main_reason"] = hits[0]["uz_text"] if hits else (ra.shap_top[0]["uz_label"] if ra and ra.shap_top else None)
        out.append(r)
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
             "from_polyclinic_id": a.from_polyclinic_id, "to_polyclinic_id": a.to_polyclinic_id, "details": a.details,
             "ip": a.ip, "user": u.username if u else "tizim", "role": u.role if u else None,
             "polyclinic": pc.code if pc else None} for a, u, pc in rows]


@router.get("/settings/sla")
def sla_settings(user: User = Depends(current_user)) -> dict:
    """Read-only SLA settings for the "Tizim haqida" page (department head and admins)."""
    if user.role not in ("department_head", *ADMIN_ROLES):
        raise HTTPException(403, "Ruxsat yo'q")
    s = get_settings()
    return {"demo_mode": s.demo_mode, "sla_red_minutes": s.sla_red_minutes,
            "demo_sla_red_minutes": s.demo_sla_red_minutes, "effective_sla_red_minutes": s.effective_sla_red_minutes,
            "sla_yellow_hours": s.sla_yellow_hours, "chain": {k: list(v) for k, v in ESCALATION_CHAIN.items()}}
