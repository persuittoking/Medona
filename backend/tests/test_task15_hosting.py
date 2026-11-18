"""Task 15: single-service hosting (SPA served by FastAPI), CORS_ORIGINS, login rate limit, start script."""
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import mount_spa
from app.security.rate_limit import SlidingWindowLimiter, login_limiter
from tests.conftest import NUK

ROOT = Path(__file__).resolve().parents[2]


# ---------------- A5: login rate limit ----------------
def test_limiter_sliding_window():
    lim = SlidingWindowLimiter()
    assert all(lim.allow("ip", 20, 600, now=float(i)) for i in range(20))
    assert not lim.allow("ip", 20, 600, now=30.0)  # 21st attempt inside 10 minutes
    assert lim.allow("other-ip", 20, 600, now=30.0)  # per IP
    assert lim.allow("ip", 20, 600, now=600.5)  # the oldest attempt left the window
    assert lim.allow("ip", 0, 600)  # 0 = off


@pytest.fixture
def limited():
    s = get_settings()
    old = s.login_rate_limit
    s.login_rate_limit = 20
    login_limiter.reset()
    yield
    s.login_rate_limit = old
    login_limiter.reset()


def test_login_limited_to_20_per_ip(client, limited):
    bad = {"polyclinic_code": NUK, "username": "nurse", "password": "wrong"}
    codes = [client.post("/api/auth/login", json=bad).status_code for _ in range(20)]
    assert codes == [401] * 20
    r = client.post("/api/auth/login", json={**bad, "password": "demo1234"})  # even the right password is refused now
    assert r.status_code == 429
    assert "daqiqadan" in r.json()["detail"]


# ---------------- A2: CORS_ORIGINS ----------------
def test_cors_origins_default_and_env():
    assert Settings(_env_file=None).cors_origin_list == ["http://localhost:5173", "http://127.0.0.1:5173"]
    s = Settings(_env_file=None, cors_origins=" https://a.up.railway.app , https://b.example ,")
    assert s.cors_origin_list == ["https://a.up.railway.app", "https://b.example"]


# ---------------- A1: SPA served from backend/static ----------------
@pytest.fixture
def spa_client(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><div id=root></div>", encoding="utf-8")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    (tmp_path.parent / "secret.txt").write_text("no", encoding="utf-8")
    app = FastAPI()

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    assert mount_spa(app, tmp_path)
    return TestClient(app)


def test_spa_routes(spa_client):
    c = spa_client
    for path in ("/", "/map", "/patients/12", "/login"):
        r = c.get(path)
        assert r.status_code == 200 and "id=root" in r.text, path
    assert c.get("/assets/app.js").text == "console.log(1)"
    assert c.get("/favicon.svg").text == "<svg/>"
    assert c.get("/api/health").json() == {"status": "ok"}
    assert c.get("/docs").status_code == 200
    for path in ("/api/nope", "/api", "/api/auth/whatever"):
        r = c.get(path)
        assert r.status_code == 404 and r.headers["content-type"].startswith("application/json"), path
    assert "no" != c.get("/..%2Fsecret.txt").text  # no path traversal: falls back to index.html


def test_no_static_dir_means_no_spa(tmp_path):
    assert not mount_spa(FastAPI(), tmp_path)


# ---------------- A3 / B: deploy files ----------------
def test_start_script_and_docker_files():
    sh = (ROOT / "backend" / "start.sh").read_bytes()
    assert b"\r\n" not in sh
    text = sh.decode()
    for name in ("JWT_SECRET", "PINFL_HASH_SECRET", "FERNET_KEY", "app.seed", "--proxy-headers"):
        assert name in text
    assert "train.py" not in text and "train_model" not in text  # never trains: the committed model artifact is used
    assert "*.sh text eol=lf" in (ROOT / ".gitattributes").read_text()
    docker = (ROOT / "Dockerfile").read_text()
    assert "libgomp1" in docker and "backend/static" in docker
    assert "/api/health" in (ROOT / "railway.json").read_text()
    assert (ROOT / "backend" / "ml" / "artifacts" / "model.joblib").is_file()
