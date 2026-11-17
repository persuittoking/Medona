"""Background jobs (APScheduler). SLA escalation runs every ESCALATION_INTERVAL_S seconds."""
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.db import SessionLocal
from app.services.alerts import run_escalations

log = logging.getLogger("onaradar.scheduler")

ESCALATION_INTERVAL_S = 30
ESCALATION_JOB_ID = "sla_escalation"


def escalation_job() -> int:
    """One escalation pass in its own DB session. Never raises: a failing job must not stop the scheduler."""
    try:
        with SessionLocal() as db:
            n = run_escalations(db)
        if n:
            log.info("escalated %d alert(s)", n)
        return n
    except Exception:  # noqa: BLE001
        log.exception("escalation job failed")
        return 0


def start_scheduler() -> BackgroundScheduler:
    sched = BackgroundScheduler(daemon=True, timezone="UTC")
    sched.add_job(escalation_job, "interval", seconds=ESCALATION_INTERVAL_S, id=ESCALATION_JOB_ID,
                  max_instances=1, coalesce=True, replace_existing=True)
    sched.start()
    log.info("scheduler started: %s every %ss", ESCALATION_JOB_ID, ESCALATION_INTERVAL_S)
    return sched
