import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

# Tests use their own SQLite file and never need real secrets.
os.environ["DATABASE_URL"] = "sqlite:///./test_onaradar.db"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ.setdefault("FERNET_KEY", "x" * 43 + "=")  # replaced below with a valid key

from cryptography.fernet import Fernet  # noqa: E402

os.environ["FERNET_KEY"] = Fernet.generate_key().decode()
os.environ["JWT_SECRET"] = "test-secret"

import pytest  # noqa: E402

NUK, CHL, FRG = "PL-NUK-001", "PL-CHL-001", "PL-FRG-001"


@pytest.fixture(scope="module")
def client():
    """A freshly seeded DB per test module (tests mutate state)."""
    from fastapi.testclient import TestClient

    from app.seed import seed

    seed(seed_value=3, active_per_mahalla=(16, 18))  # small register: fast tests
    from app.main import app

    with TestClient(app) as c:
        yield c


def login(c, polyclinic, username=None):
    """login(c, "PL-NUK-001", "nurse") for staff, login(c, None, "region.admin") for admins."""
    r = c.post("/api/auth/login", json={"polyclinic_code": polyclinic, "username": username, "password": "demo1234"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def demo(code="QQR-NUK-DEMO1"):
    from app.db import SessionLocal
    from app.models import Patient

    with SessionLocal() as db:
        p = db.query(Patient).filter_by(code=code).one()
        return p.id, p.pregnancies[0].id
