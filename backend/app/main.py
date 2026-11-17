"""OnaRadar FastAPI application."""
import contextlib
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import alerts, auth, dashboard, geo, llm, patients, visits
from app.config import get_settings
from app.db import Base, engine
from app.risk.ml import load_model
from app.scheduler import schedule_prewarm, start_scheduler

log = logging.getLogger("onaradar")


@contextlib.asynccontextmanager
async def lifespan(app_: FastAPI):
    Base.metadata.create_all(engine)
    load_model()  # warm the model + SHAP explainer
    app_.state.scheduler = start_scheduler()  # SLA escalation every 30 s
    if get_settings().llm_enabled and get_settings().llm_prewarm:
        schedule_prewarm(app_.state.scheduler)  # DEMO1-DEMO4 AI summaries, in the background
    yield
    app_.state.scheduler.shutdown(wait=False)


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
            "llm": "ai" if s.llm_enabled else "template", "llm_provider": s.llm_provider}
