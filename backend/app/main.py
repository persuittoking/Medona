"""OnaRadar FastAPI application."""
import asyncio
import contextlib
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import alerts, auth, dashboard, geo, llm, patients, visits
from app.config import get_settings
from app.db import Base, SessionLocal, engine
from app.risk.ml import load_model
from app.services.alerts import run_escalations

log = logging.getLogger("onaradar")


async def _escalation_loop() -> None:
    while True:
        await asyncio.sleep(30)
        try:
            with SessionLocal() as db:
                n = run_escalations(db)
                if n:
                    log.info("escalated %d alert(s)", n)
        except Exception:  # noqa: BLE001 - background job must never crash the app
            log.exception("escalation job failed")


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    load_model()  # warm the model + SHAP explainer
    task = asyncio.create_task(_escalation_loop())
    yield
    task.cancel()


app = FastAPI(title="OnaRadar API", version="0.1.0", lifespan=lifespan,
              description="Perinatal early-warning registry (decision support, synthetic demo data).")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])
for r in (auth.router, patients.router, visits.router, alerts.router, dashboard.router, geo.router, llm.router):
    app.include_router(r)


@app.get("/api/health", tags=["meta"])
def health() -> dict:
    s = get_settings()
    mdl = load_model()
    return {"status": "ok", "demo_mode": s.demo_mode, "model_version": mdl.version if mdl else None,
            "llm": "ai" if s.anthropic_api_key else "template"}
