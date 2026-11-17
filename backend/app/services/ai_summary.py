"""AI summary generation in the background, cached per risk assessment.

A visit save schedules `generate_cached(ra_id)`; the patient card polls GET /api/llm/summary until the cache row
exists. On startup (key present) `prewarm_demo_patients` fills the cache for the DEMO1-DEMO4 cards.
"""
from __future__ import annotations

import logging
import threading
import time

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.patients import risk_out
from app.db import SessionLocal
from app.llm.summary import build_llm_input, generate_summary
from app.models import LlmSummaryCache, Patient, Pregnancy, RiskAssessment, utcnow
from app.services.scoring import preg_dict, visit_dict

log = logging.getLogger("onaradar.ai_summary")

DEMO_CODES = ("QQR-NUK-DEMO1", "QQR-NUK-DEMO2", "QQR-NUK-DEMO3", "QQR-NUK-DEMO4")
PREWARM_GAP_S = 2.0

_lock = threading.Lock()
_in_flight: set[int] = set()


def is_pending(ra_id: int) -> bool:
    with _lock:
        return ra_id in _in_flight


def _claim(ra_id: int) -> bool:
    with _lock:
        if ra_id in _in_flight:
            return False
        _in_flight.add(ra_id)
        return True


def _release(ra_id: int) -> None:
    with _lock:
        _in_flight.discard(ra_id)


def get_cached(db: Session, ra_id: int) -> LlmSummaryCache | None:
    return db.scalars(select(LlmSummaryCache).where(LlmSummaryCache.risk_assessment_id == ra_id)).first()


def build_and_store(db: Session, ra: RiskAssessment) -> LlmSummaryCache:
    """Generate (Gemini -> fallbacks -> template) and upsert the cache row for this assessment."""
    preg = db.get(Pregnancy, ra.pregnancy_id)
    payload = build_llm_input(preg.patient.code, preg.patient.birth_date, preg_dict(preg),
                              [visit_dict(v) for v in preg.visits], risk_out(ra))
    result, tin, tout = generate_summary(payload)
    row = get_cached(db, ra.id)
    if row is None:
        row = LlmSummaryCache(risk_assessment_id=ra.id, source=result["source"], payload=result)
        db.add(row)
    row.source, row.payload, row.input_tokens, row.output_tokens = result["source"], result, tin, tout
    row.created_at = utcnow()
    try:
        db.commit()
    except IntegrityError:  # another worker stored it first: keep theirs
        db.rollback()
        row = get_cached(db, ra.id)
    return row


def generate_cached(ra_id: int, force: bool = False) -> None:
    """Background task: own DB session, never raises, at most one generation per assessment at a time."""
    if not _claim(ra_id):
        return
    try:
        with SessionLocal() as db:
            ra = db.get(RiskAssessment, ra_id)
            if ra is None or ra.pregnancy_id is None:
                return
            if force or get_cached(db, ra_id) is None:
                build_and_store(db, ra)
    except Exception:
        log.exception("background AI summary failed for assessment %s", ra_id)
    finally:
        _release(ra_id)


def latest_pregnancy_assessment(db: Session, patient: Patient) -> RiskAssessment | None:
    ids = [p.id for p in patient.pregnancies]
    if not ids:
        return None
    return db.scalars(select(RiskAssessment).where(RiskAssessment.pregnancy_id.in_(ids))
                      .order_by(RiskAssessment.id.desc()).limit(1)).first()


def prewarm_demo_patients(gap_s: float = PREWARM_GAP_S) -> int:
    """Generate summaries for the DEMO1-DEMO4 cards, spaced `gap_s` apart. Returns how many were generated."""
    with SessionLocal() as db:
        todo = []
        for code in DEMO_CODES:
            pat = db.scalars(select(Patient).where(Patient.code == code)).first()
            ra = latest_pregnancy_assessment(db, pat) if pat else None
            if ra is not None and get_cached(db, ra.id) is None:
                todo.append(ra.id)
    for i, ra_id in enumerate(todo):
        if i:
            time.sleep(gap_s)
        generate_cached(ra_id)
    if todo:
        log.info("pre-warmed %d demo AI summaries", len(todo))
    return len(todo)
