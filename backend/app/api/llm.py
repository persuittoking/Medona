from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.api.deps import require_admin
from app.api.patients import risk_out
from app.api.tenancy import Tenant, staff
from app.config import get_settings
from app.llm.summary import build_llm_input, generate_summary, llm_status
from app.models import LlmSummaryCache, RiskAssessment, User, utcnow
from app.services.scoring import preg_dict, visit_dict

router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.get("/summary/{pregnancy_id}")
def llm_summary(pregnancy_id: int, refresh: bool = False, t: Tenant = Depends(staff())) -> dict:
    """AI summary of the latest assessment. Cached per risk assessment; ?refresh=true regenerates."""
    db = t.db
    preg = t.get_pregnancy(pregnancy_id)
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


@router.get("/health")
def llm_health(_: User = Depends(require_admin)) -> dict:
    """Admin view of the LLM integration: is a key configured, did the last real call succeed, last error.

    The key itself is never returned. `last_call` is null until the first real call since the backend started.
    """
    s = get_settings()
    st = llm_status()
    last_call = None if st["last_call_ok"] is None else ("ok" if st["last_call_ok"] else "failed")
    return {
        "key_present": bool(s.anthropic_api_key),
        "mode": "ai" if s.anthropic_api_key else "template",
        "configured_model": s.llm_model,
        "last_call": last_call,
        "last_call_at": st["last_call_at"],
        "last_model": st["last_model"],
        "last_error": st["last_error"],
    }
