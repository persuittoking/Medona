"""OnaRadar FastAPI application."""
import contextlib
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import alerts, auth, care_loop, children, dashboard, geo, llm, patients, visits
from app.config import BACKEND_DIR, get_settings
from app.db import Base, engine, ensure_columns, sync_pinfl_hashes
from app.risk.ml import load_model
from app.scheduler import schedule_prewarm, start_scheduler

log = logging.getLogger("onaradar")


@contextlib.asynccontextmanager
async def lifespan(app_: FastAPI):
    get_settings().check_secrets()  # DEMO_MODE=false: refuse to start with weak / missing secrets
    Base.metadata.create_all(engine)
    added = ensure_columns(engine)  # older demo DB: add new nullable columns, never drop anything
    if added:
        log.warning("schema upgraded (added columns): %s", ", ".join(added))
    rehashed = sync_pinfl_hashes(engine)  # PINFL_HASH_SECRET changed -> recompute every stored hash
    if rehashed:
        log.warning("JShShIR lookup hashes (re)computed for %d patients", rehashed)
    load_model()  # warm the model + SHAP explainer
    app_.state.scheduler = start_scheduler()  # SLA escalation every 30 s
    if get_settings().llm_enabled and get_settings().llm_prewarm:
        schedule_prewarm(app_.state.scheduler)  # DEMO1-DEMO4 AI summaries, in the background
    yield
    app_.state.scheduler.shutdown(wait=False)


app = FastAPI(title="OnaRadar API", version="0.1.0", lifespan=lifespan,
              description="Perinatal early-warning registry (decision support, synthetic demo data).")
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origin_list,
                   allow_methods=["*"], allow_headers=["*"])
for r in (auth.router, care_loop.router, patients.router, children.router, visits.router, alerts.router, dashboard.router, geo.router, llm.router):
    app.include_router(r)


@app.get("/api/health", tags=["meta"])
def health() -> dict:
    s = get_settings()
    mdl = load_model()
    return {"status": "ok", "demo_mode": s.demo_mode, "model_version": mdl.version if mdl else None,
            "llm": "ai" if s.llm_enabled else "template", "llm_provider": s.llm_provider}


# ---- Hosted single-service mode: serve the built React app (Dockerfile copies frontend/dist to backend/static) ----
STATIC_DIR = BACKEND_DIR / "static"


def mount_spa(app_: FastAPI, static_dir: Path) -> bool:
    """If static_dir/index.html exists: serve /assets and return index.html for every other non-API GET path.
    Must be called AFTER all API routers so /api/*, /docs and /openapi.json win. Returns True if mounted."""
    index = static_dir / "index.html"
    if not index.is_file():
        return False
    if (static_dir / "assets").is_dir():
        app_.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")
    root = static_dir.resolve()

    @app_.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(404, "Not Found")  # unknown API path stays a JSON 404
        candidate = (root / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(root):  # favicon.svg etc.; no traversal
            return FileResponse(candidate)
        return FileResponse(index)  # SPA route (/map, /patients/12, ...) -> React Router

    return True


mount_spa(app, STATIC_DIR)
