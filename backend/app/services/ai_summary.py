"""AI summary generation in the background, cached per risk assessment.

A visit save schedules `generate_cached(ra_id)`; the patient card polls GET /api/llm/summary until the cache row
exists. On startup (key present) `prewarm_demo_patients` fills the cache for the DEMO1-DEMO4 cards and the demo children.
"""
from __future__ import annotations

import logging
import threading
import time

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.llm.summary import SUMMARY_VERSION, build_child_llm_input, build_llm_input, generate_summary
from app.models import LlmSummaryCache, Newborn, NewbornCheck, Patient, Pregnancy, RiskAssessment, Visit, utcnow
from app.services.children import check_dict, latest_child_assessment
from app.services.scoring import preg_dict, risk_out, visit_dict

log = logging.getLogger("onaradar.ai_summary")

DEMO_CODES = ("QQR-NUK-DEMO1", "QQR-NUK-DEMO2", "QQR-NUK-DEMO3", "QQR-NUK-DEMO4")
DEMO_CHILD_CODES = ("B-QQR-NUK-DEMO4-1", "B-QQR-NUK-DEMO5-1")
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


def _cache_row(db: Session, ra_id: int) -> LlmSummaryCache | None:
    return db.scalars(select(LlmSummaryCache).where(LlmSummaryCache.risk_assessment_id == ra_id)).first()


def get_cached(db: Session, ra_id: int) -> LlmSummaryCache | None:
    """The cached summary of this assessment, or None if missing or of an older SUMMARY_VERSION (-> regenerate)."""
    row = _cache_row(db, ra_id)
    if row is None or (row.payload or {}).get("version") != SUMMARY_VERSION:
        return None
    return row


def _visits_until(db: Session, preg: Pregnancy, ra: RiskAssessment) -> list[dict]:
    """The visits the assessment was based on (an older alert must not see later visits)."""
    visit = db.get(Visit, ra.visit_id) if ra.visit_id else None
    return [visit_dict(v) for v in preg.visits if visit is None or v.visit_date <= visit.visit_date]


def _checks_until(db: Session, nb: Newborn, ra: RiskAssessment) -> list[dict]:
    """The checks a child assessment was based on, with their computed overdue-vaccine lists."""
    ck = db.get(NewbornCheck, ra.check_id) if ra.check_id else None
    return [check_dict(c) | {"vaccines_due_overdue": c.vaccines_due_overdue or []}
            for c in nb.checks if ck is None or c.check_date <= ck.check_date]


def llm_payload(db: Session, ra: RiskAssessment) -> dict:
    """The de-identified LLM input for an assessment (pregnancy or child)."""
    if ra.newborn_id is not None:
        nb = db.get(Newborn, ra.newborn_id)
        return build_child_llm_input(nb.code, nb.birth_date, nb.sex, _checks_until(db, nb, ra), risk_out(ra),
                                     today=ra.created_at.date())
    preg = db.get(Pregnancy, ra.pregnancy_id)
    return build_llm_input(preg.patient.code, preg.patient.birth_date, preg_dict(preg),
                           _visits_until(db, preg, ra), risk_out(ra))


def build_and_store(db: Session, ra: RiskAssessment) -> LlmSummaryCache:
    """Generate (Gemini -> fallbacks -> template) and upsert the cache row for this assessment."""
    payload = llm_payload(db, ra)
    result, tin, tout = generate_summary(payload)
    row = _cache_row(db, ra.id)
    if row is None:
        row = LlmSummaryCache(risk_assessment_id=ra.id, source=result["source"], payload=result)
        db.add(row)
    row.source, row.payload, row.input_tokens, row.output_tokens = result["source"], result, tin, tout
    row.created_at = utcnow()
    try:
        db.commit()
    except IntegrityError:  # another worker stored it first: keep theirs
        db.rollback()
        row = _cache_row(db, ra.id)
    return row


def alert_summary(db: Session, ra_id: int) -> dict:
    """The 3 doctor bullets for an alert, from the cached summary of its risk assessment.

    {"summary_status": "ready", "summary_bullets": [...], "summary_source": "ai"|"template"} or
    {"summary_status": "pending", "summary_bullets": None, "summary_source": None} while not generated yet.
    """
    row = get_cached(db, ra_id)
    if row is None:
        return {"summary_status": "pending", "summary_bullets": None, "summary_source": None}
    return {"summary_status": "ready", "summary_bullets": row.payload.get("doctor_bullets_uz"),
            "summary_source": row.source}


def generate_cached(ra_id: int, force: bool = False) -> None:
    """Background task: own DB session, never raises, at most one generation per assessment at a time."""
    if not _claim(ra_id):
        return
    try:
        with SessionLocal() as db:
            ra = db.get(RiskAssessment, ra_id)
            if ra is None or (ra.pregnancy_id is None and ra.newborn_id is None):
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


def demo_summary_status(db: Session) -> dict:
    """COUNTS only (admin health check): how many DEMO1-DEMO4 (+ demo children) latest assessments have a cached
    summary, and from which source. No codes, no content."""
    out = {"total": 0, "cached": 0, "ai": 0, "template": 0}
    ras = []
    for code in DEMO_CODES:
        pat = db.scalars(select(Patient).where(Patient.code == code)).first()
        ras.append(latest_pregnancy_assessment(db, pat) if pat else None)
    for code in DEMO_CHILD_CODES:
        nb = db.scalars(select(Newborn).where(Newborn.code == code)).first()
        ras.append(latest_child_assessment(db, nb.id) if nb else None)
    for ra in ras:
        if ra is None:
            continue
        out["total"] += 1
        cached = get_cached(db, ra.id)
        if cached is not None:
            out["cached"] += 1
            out["ai" if cached.source == "ai" else "template"] += 1
    return out


def prewarm_demo_patients(gap_s: float = PREWARM_GAP_S) -> int:
    """Generate summaries for the DEMO1-DEMO4 cards, spaced `gap_s` apart. Returns how many were generated."""
    with SessionLocal() as db:
        todo = []
        for code in DEMO_CODES:
            pat = db.scalars(select(Patient).where(Patient.code == code)).first()
            ra = latest_pregnancy_assessment(db, pat) if pat else None
            if ra is not None and get_cached(db, ra.id) is None:
                todo.append(ra.id)
        for code in DEMO_CHILD_CODES:
            nb = db.scalars(select(Newborn).where(Newborn.code == code)).first()
            ra = latest_child_assessment(db, nb.id) if nb else None
            if ra is not None and get_cached(db, ra.id) is None:
                todo.append(ra.id)
    for i, ra_id in enumerate(todo):
        if i:
            time.sleep(gap_s)
        generate_cached(ra_id)
    if todo:
        log.info("pre-warmed %d demo AI summaries", len(todo))
    return len(todo)
