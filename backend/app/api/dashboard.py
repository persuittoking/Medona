import json
import statistics
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, require_roles, scope_patients
from app.config import BACKEND_DIR
from app.db import get_db
from app.models import Alert, AuditLog, District, Patient, Pregnancy, RiskAssessment, User, utcnow
from app.risk.features import gest_weeks
from app.security.crypto import decrypt, mask_name
from app.services.alerts import run_escalations

router = APIRouter(prefix="/api", tags=["dashboard"])


def _scoped_pregnancies(db: Session, user: User, district_id: int | None) -> list[tuple[Pregnancy, Patient]]:
    stmt = select(Pregnancy, Patient).join(Patient, Pregnancy.patient_id == Patient.id).where(Pregnancy.status == "active")
    stmt = scope_patients(stmt, user)
    if district_id:
        stmt = stmt.where(Patient.district_id == district_id)
    return list(db.execute(stmt).all())


def _scoped_alerts(db: Session, user: User, district_id: int | None) -> list[Alert]:
    stmt = select(Alert).join(Pregnancy, Alert.pregnancy_id == Pregnancy.id).join(Patient, Pregnancy.patient_id == Patient.id)
    stmt = scope_patients(stmt, user)
    if district_id:
        stmt = stmt.where(Patient.district_id == district_id)
    return list(db.scalars(stmt).all())


@router.get("/dashboard/summary")
def summary(district_id: int | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    run_escalations(db)
    pregs = _scoped_pregnancies(db, user, district_id)
    alerts = _scoped_alerts(db, user, district_id)
    now = utcnow()
    zones = {z: sum(1 for p, _ in pregs if p.current_zone == z) for z in ("red", "yellow", "green")}
    active_alerts = [a for a in alerts if a.status in ("open", "escalated")]
    breaches = [a for a in alerts if (a.status in ("open", "escalated") and a.sla_due_at < now) or a.escalation_level > 0
                or (a.acknowledged_at and a.acknowledged_at > a.sla_due_at)]
    ack_minutes = [(a.acknowledged_at - a.created_at).total_seconds() / 60 for a in alerts if a.acknowledged_at]
    return {
        "active_pregnancies": len(pregs), **zones,
        "open_alerts": len(active_alerts),
        "open_red_alerts": sum(1 for a in active_alerts if a.level == "red"),
        "sla_breaches": len(breaches),
        "median_ack_minutes": round(statistics.median(ack_minutes), 1) if ack_minutes else None,
        "synthetic": True,
    }


@router.get("/dashboard/districts")
def districts(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    pregs = _scoped_pregnancies(db, user, None)
    out: dict[int, dict] = {}
    for p, pat in pregs:
        d = out.get(pat.district_id)
        if d is None:
            dist = db.get(District, pat.district_id)
            d = out[pat.district_id] = {"district_id": dist.id, "name": dist.name, "region_id": dist.region_id,
                                        "lat": dist.lat, "lon": dist.lon, "red": 0, "yellow": 0, "green": 0, "total": 0}
        d[p.current_zone] += 1
        d["total"] += 1
    for d in out.values():
        d["red_share"] = round(d["red"] / d["total"], 3) if d["total"] else 0.0
    return sorted(out.values(), key=lambda d: -d["red_share"])


@router.get("/dashboard/trend")
def trend(weeks: int = 12, district_id: int | None = None, user: User = Depends(current_user),
          db: Session = Depends(get_db)) -> list[dict]:
    start = date.today() - timedelta(weeks=weeks)
    stmt = (select(RiskAssessment.created_at, RiskAssessment.zone, RiskAssessment.pregnancy_id)
            .join(Pregnancy, RiskAssessment.pregnancy_id == Pregnancy.id).join(Patient, Pregnancy.patient_id == Patient.id)
            .where(RiskAssessment.created_at >= start, RiskAssessment.zone != "green"))
    stmt = scope_patients(stmt, user)
    if district_id:
        stmt = stmt.where(Patient.district_id == district_id)
    buckets: dict[int, dict[str, set]] = {i: {"red": set(), "yellow": set()} for i in range(weeks + 1)}
    for created, zone, pid in db.execute(stmt).all():
        idx = min(weeks, (created.date() - start).days // 7)
        buckets[idx][zone].add(pid)
    return [{"week_start": str(start + timedelta(weeks=i)), "red": len(b["red"]), "yellow": len(b["yellow"])}
            for i, b in buckets.items()]


@router.get("/dashboard/top")
def top(limit: int = 10, district_id: int | None = None, user: User = Depends(current_user),
        db: Session = Depends(get_db)) -> list[dict]:
    order = {"red": 0, "yellow": 1, "green": 2}
    pregs = sorted(_scoped_pregnancies(db, user, district_id),
                   key=lambda t: (order[t[0].current_zone], -(t[0].current_risk_score or 0)))[:limit]
    out = []
    for p, pat in pregs:
        ra = db.scalars(select(RiskAssessment).where(RiskAssessment.pregnancy_id == p.id)
                        .order_by(RiskAssessment.id.desc())).first()
        out.append({"patient_id": pat.id, "pregnancy_id": p.id, "code": pat.code,
                    "name_masked": mask_name(decrypt(pat.full_name_enc)), "district_name": pat.district.name,
                    "gestational_weeks": gest_weeks(p.lmp_date, date.today()), "zone": p.current_zone,
                    "risk": p.current_risk_score,
                    "main_reason": ((ra.rule_hits + ra.trend_hits)[0]["uz_text"] if ra and (ra.rule_hits + ra.trend_hits)
                                    else (ra.shap_top[0]["uz_label"] if ra and ra.shap_top else None))})
    return out


@router.get("/districts")
def list_districts(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    stmt = select(District)
    if user.role != "admin":
        stmt = stmt.where(District.id == user.district_id)
    else:
        stmt = stmt.where(District.region_id == user.region_id)
    return [{"id": d.id, "name": d.name, "region_id": d.region_id} for d in db.scalars(stmt).all()]


@router.get("/analytics/model")
def model_metrics(user: User = Depends(current_user)) -> dict:
    path = BACKEND_DIR / "ml" / "artifacts" / "metrics.json"
    if not path.exists():
        raise HTTPException(404, "Model hali o'qitilmagan (ml/train.py)")
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/audit")
def audit_log(action: str | None = None, user_id: int | None = None, entity: str | None = None, limit: int = 200,
              user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)) -> list[dict]:
    stmt = select(AuditLog, User).outerjoin(User, AuditLog.user_id == User.id)
    stmt = stmt.where((User.region_id == user.region_id) | (AuditLog.user_id.is_(None)))
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if entity:
        stmt = stmt.where(AuditLog.entity == entity)
    rows = db.execute(stmt.order_by(AuditLog.id.desc()).limit(min(limit, 1000))).all()
    return [{"id": a.id, "created_at": a.created_at, "action": a.action, "entity": a.entity, "entity_id": a.entity_id,
             "ip": a.ip, "user": u.username if u else "tizim", "role": u.role if u else None} for a, u in rows]
