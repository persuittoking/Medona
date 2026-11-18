from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.api.tenancy import Tenant, staff
from app.config import get_settings
from app.db import get_db
from app.llm.summary import llm_status
from app.models import RiskAssessment, User
from app.services.ai_summary import build_and_store, demo_summary_status, generate_cached, get_cached, is_pending
from app.services.children import latest_child_assessment
from app.services.scoring import latest_assessment

router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.get("/summary/{pregnancy_id}")
def llm_summary(pregnancy_id: int, background: BackgroundTasks, response: Response, refresh: bool = False,
                t: Tenant = Depends(staff())) -> dict:
    """AI summary of the latest assessment, cached per risk assessment.

    Never blocks on Gemini: if the summary is not cached yet it is generated in the background and this returns
    202 {"status": "pending"}; the card polls until 200 {"status": "ready", ...}. ?refresh=true regenerates.
    Without an API key the template ("Shablon") is instant, so it is built inline.
    """
    preg = t.get_pregnancy(pregnancy_id)
    ra = latest_assessment(t.db, preg.id)
    if ra is None:
        raise HTTPException(404, "Bu homiladorlik uchun hali baholash yo'q")
    return _summary(t, ra, background, response, refresh)


@router.get("/summary/child/{newborn_id}")
def llm_child_summary(newborn_id: int, background: BackgroundTasks, response: Response, refresh: bool = False,
                      t: Tenant = Depends(staff())) -> dict:
    """Same contract as /summary/{pregnancy_id}, for a child's latest assessment (child allow-list payload)."""
    nb = t.get_newborn(newborn_id)
    ra = latest_child_assessment(t.db, nb.id)
    if ra is None:
        raise HTTPException(404, "Bu bola uchun hali baholash yo'q")
    return _summary(t, ra, background, response, refresh)


def _summary(t: Tenant, ra: RiskAssessment, background: BackgroundTasks, response: Response, refresh: bool) -> dict:
    db = t.db
    cached = get_cached(db, ra.id)
    if cached is not None and refresh and not is_pending(ra.id):
        db.delete(cached)
        db.commit()
        cached = None
    if cached is None and not get_settings().llm_enabled:
        cached = build_and_store(db, ra)
    if cached is None:
        if not is_pending(ra.id):
            background.add_task(generate_cached, ra.id)
        response.status_code = 202
        return {"status": "pending", "risk_assessment_id": ra.id}
    return {**cached.payload, "status": "ready", "risk_assessment_id": ra.id, "generated_at": cached.created_at}


@router.get("/health")
def llm_health(_: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    """Admin view of the LLM integration: is a key configured, did the last real call succeed, last error.

    The key itself is never returned. `last_call` is null until the first real call since the backend started.
    """
    s = get_settings()
    st = llm_status()
    last_call = None if st["last_call_ok"] is None else ("ok" if st["last_call_ok"] else "failed")
    return {
        "provider": s.llm_provider,
        "key_present": bool(s.gemini_api_key),
        "mode": "ai" if s.llm_enabled else "template",
        "configured_model": s.gemini_model,
        "fallback_model": s.gemini_fallback_model or None,
        "timeout_s": s.llm_timeout_s,
        "last_call": last_call,
        "last_call_at": st["last_call_at"],
        "last_model": st["last_model"],
        "last_error": st["last_error"],
        "last_attempts": st.get("last_attempts", []),
        "demo_summaries": demo_summary_status(db),  # counts only: are the DEMO cards' summaries ready?
    }
