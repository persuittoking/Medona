from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_pregnancy_checked
from app.api.patients import risk_out
from app.db import get_db
from app.llm.summary import build_llm_input, generate_summary
from app.models import LlmSummaryCache, RiskAssessment, User, utcnow
from app.services.scoring import preg_dict, visit_dict

router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.get("/summary/{pregnancy_id}")
def llm_summary(pregnancy_id: int, refresh: bool = False, user: User = Depends(current_user),
                db: Session = Depends(get_db)) -> dict:
    """AI summary of the latest assessment. Cached per risk assessment; ?refresh=true regenerates."""
    preg = get_pregnancy_checked(db, pregnancy_id, user)
    ra = db.scalars(select(RiskAssessment).where(RiskAssessment.pregnancy_id == preg.id)
                    .order_by(RiskAssessment.id.desc())).first()
    if ra is None:
        raise HTTPException(404, "Bu homiladorlik uchun hali baholash yo'q")
    cached = db.scalars(select(LlmSummaryCache).where(LlmSummaryCache.risk_assessment_id == ra.id)).first()
    if cached is not None and not refresh:
        return {**cached.payload, "risk_assessment_id": ra.id, "generated_at": cached.created_at}

    payload = build_llm_input(preg.patient.code, preg.patient.birth_date, preg_dict(preg),
                              [visit_dict(v) for v in preg.visits], risk_out(ra))
    result, tin, tout = generate_summary(payload)
    if cached is None:
        cached = LlmSummaryCache(risk_assessment_id=ra.id, source=result["source"], payload=result)
        db.add(cached)
    cached.source, cached.payload, cached.input_tokens, cached.output_tokens = result["source"], result, tin, tout
    cached.created_at = utcnow()
    db.commit()
    return {**result, "risk_assessment_id": ra.id, "generated_at": cached.created_at}
