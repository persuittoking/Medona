from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import audit
from app.api.tenancy import Tenant, staff
from app.api.patients import risk_out
from app.models import Visit
from app.risk.features import gest_weeks
from app.schemas import RiskOut, VisitCreatedOut, VisitIn
from app.services.alerts import alert_out
from app.services.scoring import apply_assessment, create_alert_if_worse, score_new_visit, store_assessment

router = APIRouter(prefix="/api", tags=["visits"])


def _visit_payload(body: VisitIn, lmp: date) -> dict:
    d = body.model_dump(exclude={"pregnancy_id"})
    d["visit_date"] = d["visit_date"] or date.today()
    if d["visit_date"] > date.today():
        raise HTTPException(422, "Tashrif sanasi kelajakda bo'lishi mumkin emas")
    d["gestational_weeks"] = gest_weeks(lmp, d["visit_date"])
    return d


@router.post("/risk/preview", response_model=RiskOut)
def risk_preview(body: VisitIn, t: Tenant = Depends(staff())) -> dict:
    """Score a visit WITHOUT saving anything (live preview while the nurse types)."""
    preg = t.get_pregnancy(body.pregnancy_id)
    return score_new_visit(t.db, preg, _visit_payload(body, preg.lmp_date))


@router.post("/visits", response_model=VisitCreatedOut, status_code=201)
def create_visit(body: VisitIn, request: Request, t: Tenant = Depends(staff("nurse", "doctor"))) -> dict:
    db, user = t.db, t.user
    preg = t.get_pregnancy(body.pregnancy_id)
    if preg.status != "active":
        raise HTTPException(409, "Bu homiladorlik faol emas")
    payload = _visit_payload(body, preg.lmp_date)
    result = score_new_visit(db, preg, payload)
    old_zone = preg.current_zone
    visit = Visit(pregnancy_id=preg.id, entered_by=user.id, notes=payload.pop("notes"), **payload)
    db.add(visit)
    db.flush()
    ra = store_assessment(db, preg, visit, result)
    alert = create_alert_if_worse(db, preg, old_zone, ra)
    apply_assessment(preg, ra)
    audit(db, user, "create_visit", "visit", visit.id, request)
    if alert is not None:
        audit(db, None, "create_alert", "alert", alert.id, request)
    db.commit()
    db.refresh(visit)
    return {"visit": visit, "assessment": risk_out(ra), "previous_zone": old_zone,
            "alert": alert_out(alert, db) if alert else None}
