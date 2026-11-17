"""Background jobs (APScheduler). SLA escalation runs every ESCALATION_INTERVAL_S seconds."""
import logging
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from app.db import SessionLocal
from app.services.alerts import run_escalations

log = logging.getLogger("onaradar.scheduler")

ESCALATION_INTERVAL_S = 30
ESCALATION_JOB_ID = "sla_escalation"
PREWARM_JOB_ID = "ai_summary_prewarm"


def escalation_job() -> int:
    """One escalation pass in its own DB session. Never raises: a failing job must not stop the scheduler."""
    try:
        with SessionLocal() as db:
            n = run_escalations(db)
        if n:
            log.info("escalated %d alert(s)", n)
        return n
    except Exception:
        log.exception("escalation job failed")
        return 0


def start_scheduler() -> BackgroundScheduler:
    sched = BackgroundScheduler(daemon=True, timezone="UTC")
    sched.add_job(escalation_job, "interval", seconds=ESCALATION_INTERVAL_S, id=ESCALATION_JOB_ID,
                  max_instances=1, coalesce=True, replace_existing=True)
    sched.start()
    log.info("scheduler started: %s every %ss", ESCALATION_JOB_ID, ESCALATION_INTERVAL_S)
    return sched


def prewarm_job() -> int:
    try:
        from app.services.ai_summary import prewarm_demo_patients

        return prewarm_demo_patients()
    except Exception:
        log.exception("AI summary pre-warm failed")
        return 0


def schedule_prewarm(sched: BackgroundScheduler, delay_s: float = 3.0) -> None:
    """One-off job shortly after startup, so the server is already answering requests."""
    sched.add_job(prewarm_job, "date", run_date=datetime.now(UTC) + timedelta(seconds=delay_s),
                  id=PREWARM_JOB_ID, replace_existing=True, misfire_grace_time=60)
