"""API tests on a freshly seeded test database (tests/conftest.py points DATABASE_URL at a test file)."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.models import Alert, AuditLog, Patient, RiskAssessment, Visit, utcnow
from app.seed import seed

DEMO1_RED_VISIT = {"systolic": 152, "diastolic": 98, "proteinuria": "+2", "symptoms": ["severe_headache"],
                   "hemoglobin_g_l": 103, "weight_kg": 66.4}


@pytest.fixture(scope="module")
def client():
    seed(n=40, seed_value=3)
    from app.main import app

    with TestClient(app) as c:
        yield c


def login(c, username):
    r = c.post("/api/auth/login", json={"username": username, "password": "demo1234"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def demo(code="QQR-NUK-DEMO1"):
    with SessionLocal() as db:
        p = db.query(Patient).filter_by(code=code).one()
        return p.id, p.pregnancies[0].id


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_login_wrong_password(client):
    assert client.post("/api/auth/login", json={"username": "nurse.nukus", "password": "x"}).status_code == 401


def test_requires_auth(client):
    assert client.get("/api/patients").status_code == 401


def test_nurse_sees_only_own_patients(client):
    h = login(client, "nurse.nukus")
    rows = client.get("/api/patients", headers=h).json()
    assert rows and all(r["district_name"] == "Nukus tumani" for r in rows)
    other = client.get("/api/patients", headers=login(client, "nurse.chilonzor")).json()
    assert other and client.get(f"/api/patients/{other[0]['patient_id']}", headers=h).status_code == 403


def test_specialist_district_scope(client):
    h = login(client, "specialist.chilonzor")
    pid, _ = demo()
    assert client.get(f"/api/patients/{pid}", headers=h).status_code == 403
    assert client.get(f"/api/patients/{pid}", headers=login(client, "specialist.nukus")).status_code == 200


def test_admin_region_scope(client):
    pid, _ = demo()
    assert client.get(f"/api/patients/{pid}", headers=login(client, "admin.toshkent")).status_code == 403
    assert client.get(f"/api/patients/{pid}", headers=login(client, "admin.qoraqalpogiston")).status_code == 200


def test_role_boundaries(client):
    _, preg = demo()
    spec = login(client, "specialist.nukus")
    assert client.post("/api/visits", json={"pregnancy_id": preg, **DEMO1_RED_VISIT}, headers=spec).status_code == 403
    assert client.get("/api/audit", headers=login(client, "nurse.nukus")).status_code == 403
    assert client.get("/api/audit", headers=login(client, "doctor.nukus")).status_code == 403
    alerts = client.get("/api/alerts", headers=spec).json()
    if alerts:
        r = client.post(f"/api/alerts/{alerts[0]['id']}/ack", json={"action_taken": "test"}, headers=login(client, "nurse.nukus"))
        assert r.status_code == 403


def test_patient_detail_masks_pii_and_audits(client):
    pid, _ = demo()
    h = login(client, "nurse.nukus")
    with SessionLocal() as db:
        before = db.query(AuditLog).filter_by(action="view_patient", entity_id=pid).count()
    d = client.get(f"/api/patients/{pid}", headers=h).json()
    assert d["name_masked"] == "D. K." and "*" in d["pinfl_masked"] and "Dilnoza" not in str(d)
    assert d["latest_assessment"]["zone"] == "yellow"
    pii = client.post(f"/api/patients/{pid}/reveal", headers=h).json()
    assert pii["full_name"] == "Dilnoza Karimova" and len(pii["pinfl"]) == 14
    with SessionLocal() as db:
        assert db.query(AuditLog).filter_by(action="view_patient", entity_id=pid).count() == before + 1
        assert db.query(AuditLog).filter_by(action="reveal_pii", entity_id=pid).count() >= 1


def test_preview_does_not_write(client):
    _, preg = demo()
    with SessionLocal() as db:
        n_v, n_ra = db.query(Visit).count(), db.query(RiskAssessment).count()
    r = client.post("/api/risk/preview", json={"pregnancy_id": preg, **DEMO1_RED_VISIT}, headers=login(client, "nurse.nukus"))
    assert r.status_code == 200 and r.json()["zone"] == "red"
    assert "R02" in {h["code"] for h in r.json()["rule_hits"]}
    with SessionLocal() as db:
        assert (db.query(Visit).count(), db.query(RiskAssessment).count()) == (n_v, n_ra)


def test_validation_rejects_impossible_values(client):
    _, preg = demo()
    r = client.post("/api/risk/preview", json={"pregnancy_id": preg, "systolic": 400}, headers=login(client, "nurse.nukus"))
    assert r.status_code == 422


def test_demo_story_visit_creates_red_alert_then_ack(client):
    pid, preg = demo()
    r = client.post("/api/visits", json={"pregnancy_id": preg, **DEMO1_RED_VISIT}, headers=login(client, "nurse.nukus"))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["previous_zone"] == "yellow" and body["assessment"]["zone"] == "red"
    alert = body["alert"]
    assert alert and alert["level"] == "red" and alert["status"] == "open"
    spec = login(client, "specialist.nukus")
    inbox = client.get("/api/alerts?status=active", headers=spec).json()
    assert alert["id"] in {a["id"] for a in inbox}
    assert client.post(f"/api/alerts/{alert['id']}/ack", json={"action_taken": ""}, headers=spec).status_code == 422
    ok = client.post(f"/api/alerts/{alert['id']}/ack", json={"action_taken": "Perinatal markazga yo'llandi"}, headers=spec)
    assert ok.status_code == 200 and ok.json()["status"] == "acknowledged"
    assert client.post(f"/api/alerts/{alert['id']}/ack", json={"action_taken": "again"}, headers=spec).status_code == 409
    with SessionLocal() as db:
        assert db.query(AuditLog).filter_by(action="create_visit").count() >= 1
        assert db.query(AuditLog).filter_by(action="ack_alert", entity_id=alert["id"]).count() == 1


def test_no_alert_when_zone_not_worse(client):
    _, preg = demo("QQR-NUK-DEMO3")
    r = client.post("/api/visits", json={"pregnancy_id": preg, "systolic": 112, "diastolic": 70, "hemoglobin_g_l": 124,
                                         "proteinuria": "neg"}, headers=login(client, "nurse.nukus")).json()
    assert r["alert"] is None


def test_escalation_after_sla(client):
    _, preg = demo("QQR-NUK-DEMO2")
    r = client.post("/api/visits", json={"pregnancy_id": preg, "systolic": 165, "diastolic": 112},
                    headers=login(client, "nurse.nukus")).json()
    aid = r["alert"]["id"]
    with SessionLocal() as db:
        a = db.get(Alert, aid)
        a.sla_due_at = utcnow() - timedelta(minutes=1)
        db.commit()
    alerts = {a["id"]: a for a in client.get("/api/alerts", headers=login(client, "specialist.nukus")).json()}
    assert alerts[aid]["status"] == "escalated" and alerts[aid]["escalation_level"] == 1
    assert "Oilaviy shifokor" in alerts[aid]["assigned_to"]


def test_dashboard_endpoints(client):
    h = login(client, "admin.qoraqalpogiston")
    s = client.get("/api/dashboard/summary", headers=h).json()
    assert s["active_pregnancies"] == s["red"] + s["yellow"] + s["green"] > 0
    d = client.get("/api/dashboard/districts", headers=h).json()
    assert d and all("lat" in x and 0 <= x["red_share"] <= 1 for x in d)
    assert len(client.get("/api/dashboard/trend", headers=h).json()) == 13
    assert len(client.get("/api/dashboard/top", headers=h).json()) <= 10
    assert client.get("/api/analytics/model", headers=h).status_code == 200
    logs = client.get("/api/audit", headers=h).json()
    assert any(row["action"] == "login" for row in logs)


def test_llm_summary_endpoint_template_and_cache(client):
    _, preg = demo("QQR-NUK-DEMO2")
    h = login(client, "specialist.nukus")
    r1 = client.get(f"/api/llm/summary/{preg}", headers=h)
    assert r1.status_code == 200, r1.text
    body = r1.json()
    assert body["source"] == "template" and body["summary_uz"] and body["disclaimer_uz"]
    r2 = client.get(f"/api/llm/summary/{preg}", headers=h).json()
    assert r2["generated_at"] == body["generated_at"]  # served from cache
    assert client.get(f"/api/llm/summary/{preg}", headers=login(client, "specialist.chilonzor")).status_code == 403
