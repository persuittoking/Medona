"""API tests on a freshly seeded test database (tests/conftest.py points DATABASE_URL at a test file)."""
from datetime import timedelta

from app.db import SessionLocal
from app.models import Alert, AuditLog, RiskAssessment, Visit, utcnow
from app.scheduler import ESCALATION_INTERVAL_S, ESCALATION_JOB_ID, escalation_job
from tests.conftest import CHL, NUK, demo, login

DEMO1_RED_VISIT = {"systolic": 152, "diastolic": 98, "proteinuria": "+2", "symptoms": ["severe_headache"],
                   "hemoglobin_g_l": 103, "weight_kg": 66.4}


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_login_needs_right_polyclinic_and_password(client):
    def post(body: dict) -> int:
        return client.post("/api/auth/login", json={"password": "demo1234", **body}).status_code

    assert post({"polyclinic_code": NUK, "username": "nurse"}) == 200
    assert post({"polyclinic_code": "pl-nuk-001", "username": "NURSE"}) == 200  # case-insensitive
    assert post({"polyclinic_code": "PL-XXX-999", "username": "nurse"}) == 401
    assert post({"username": "nurse"}) == 401  # staff need a polyclinic ID
    assert post({"polyclinic_code": NUK, "username": "region.admin"}) == 401
    assert post({"username": "region.admin"}) == 200
    assert client.post("/api/auth/login", json={"polyclinic_code": NUK, "username": "nurse", "password": "x"}).status_code == 401


def test_requires_auth(client):
    assert client.get("/api/patients").status_code == 401


def test_staff_see_only_their_polyclinic(client):
    rows = client.get("/api/patients", headers=login(client, NUK, "nurse")).json()
    assert rows and all(r["code"].startswith("QQR-NUK-") for r in rows)
    other = client.get("/api/patients", headers=login(client, CHL, "nurse")).json()
    assert other and not {r["patient_id"] for r in rows} & {r["patient_id"] for r in other}


def test_role_boundaries(client):
    _, preg = demo()
    spec = login(client, NUK, "specialist")
    assert client.post("/api/visits", json={"pregnancy_id": preg, **DEMO1_RED_VISIT}, headers=spec).status_code == 403
    assert client.get("/api/audit", headers=login(client, NUK, "nurse")).status_code == 403
    assert client.get("/api/audit", headers=login(client, NUK, "doctor")).status_code == 403
    alerts = client.get("/api/alerts", headers=spec).json()
    if alerts:
        r = client.post(f"/api/alerts/{alerts[0]['id']}/ack", json={"action_taken": "test"}, headers=login(client, NUK, "nurse"))
        assert r.status_code == 403


def test_patient_detail_masks_pii_and_audits(client):
    pid, _ = demo()
    h = login(client, NUK, "nurse")
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
    r = client.post("/api/risk/preview", json={"pregnancy_id": preg, **DEMO1_RED_VISIT}, headers=login(client, NUK, "nurse"))
    assert r.status_code == 200 and r.json()["zone"] == "red"
    assert "R02" in {h["code"] for h in r.json()["rule_hits"]}
    with SessionLocal() as db:
        assert (db.query(Visit).count(), db.query(RiskAssessment).count()) == (n_v, n_ra)


def test_validation_rejects_impossible_values(client):
    _, preg = demo()
    r = client.post("/api/risk/preview", json={"pregnancy_id": preg, "systolic": 400}, headers=login(client, NUK, "nurse"))
    assert r.status_code == 422


def test_demo_story_visit_creates_red_alert_then_ack(client):
    pid, preg = demo()
    r = client.post("/api/visits", json={"pregnancy_id": preg, **DEMO1_RED_VISIT}, headers=login(client, NUK, "nurse"))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["previous_zone"] == "yellow" and body["assessment"]["zone"] == "red"
    alert = body["alert"]
    assert alert and alert["level"] == "red" and alert["status"] == "open"
    spec = login(client, NUK, "specialist")
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
                                         "proteinuria": "neg"}, headers=login(client, NUK, "nurse")).json()
    assert r["alert"] is None


def test_escalation_after_sla(client):
    client.app.state.scheduler.pause()  # run the job by hand, no race with the 30 s timer
    _, preg = demo("QQR-NUK-DEMO2")
    r = client.post("/api/visits", json={"pregnancy_id": preg, "systolic": 165, "diastolic": 112},
                    headers=login(client, NUK, "nurse")).json()
    aid = r["alert"]["id"]
    with SessionLocal() as db:
        a = db.get(Alert, aid)
        a.sla_due_at = utcnow() - timedelta(minutes=1)
        db.commit()
    h = login(client, NUK, "specialist")
    before = {a["id"]: a for a in client.get("/api/alerts", headers=h).json()}
    assert before[aid]["status"] == "open"  # GET endpoints no longer escalate; the background job does
    assert escalation_job() >= 1
    alerts = {a["id"]: a for a in client.get("/api/alerts", headers=h).json()}
    assert alerts[aid]["status"] == "escalated" and alerts[aid]["escalation_level"] == 1
    assert "bo'lim mudiri" in alerts[aid]["assigned_to"]  # RED chain (task 07): specialist -> department head
    with SessionLocal() as db:
        assert db.query(AuditLog).filter_by(action="escalate_alert_l1", entity="alert", entity_id=aid).count() == 1
    client.app.state.scheduler.resume()


def test_demo_expire_sla_button(client, monkeypatch):
    from app.api import alerts as alerts_api

    client.app.state.scheduler.pause()
    _, preg = demo("QQR-NUK-DEMO3")
    r = client.post("/api/visits", json={"pregnancy_id": preg, "systolic": 166, "diastolic": 112},
                    headers=login(client, NUK, "nurse")).json()
    aid = r["alert"]["id"]
    h = login(client, NUK, "specialist")
    # only the specialist may press it; admins and other roles are refused
    for who in (login(client, NUK, "nurse"), login(client, NUK, "doctor"), login(client, None, "region.admin")):
        assert client.post(f"/api/alerts/{aid}/demo-expire-sla", headers=who).status_code == 403
    assert client.post(f"/api/alerts/{aid}/demo-expire-sla", headers=login(client, CHL, "specialist")).status_code == 404
    r = client.post(f"/api/alerts/{aid}/demo-expire-sla", headers=h)
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        assert db.get(Alert, aid).sla_due_at <= utcnow()
        assert db.query(AuditLog).filter_by(action="demo_expire_sla", entity_id=aid).count() == 1
    assert escalation_job() >= 1
    with SessionLocal() as db:
        assert db.get(Alert, aid).escalation_level == 1
    # outside DEMO_MODE the endpoint does not exist
    real = alerts_api.get_settings()
    monkeypatch.setattr(alerts_api, "get_settings", lambda: real.model_copy(update={"demo_mode": False}))
    assert client.post(f"/api/alerts/{aid}/demo-expire-sla", headers=h).status_code == 404
    client.app.state.scheduler.resume()


def test_demo_sla_minutes_setting():
    from app.config import Settings

    assert Settings(_env_file=None, demo_mode=True).effective_sla_red_minutes == 10
    assert Settings(_env_file=None, demo_mode=True, demo_sla_red_minutes=7).effective_sla_red_minutes == 7
    assert Settings(_env_file=None, demo_mode=False).effective_sla_red_minutes == 120


def test_escalation_scheduler_started_on_startup(client):
    sched = client.app.state.scheduler
    assert sched.running
    job = sched.get_job(ESCALATION_JOB_ID)
    assert job is not None and job.trigger.interval.total_seconds() == ESCALATION_INTERVAL_S == 30


def test_escalation_job_never_raises(monkeypatch):
    import app.scheduler as sch

    def boom(_db):
        raise RuntimeError("db down")

    monkeypatch.setattr(sch, "run_escalations", boom)
    assert sch.escalation_job() == 0


def test_dashboard_endpoints(client):
    h = login(client, NUK, "doctor")
    s = client.get("/api/dashboard/summary", headers=h).json()
    assert s["active_pregnancies"] == s["red"] + s["yellow"] + s["green"] > 0
    assert len(client.get("/api/dashboard/trend", headers=h).json()) == 13
    top = client.get("/api/dashboard/top", headers=h).json()
    assert len(top) <= 10 and all(r["code"].startswith("QQR-NUK-") for r in top)
    assert client.get("/api/analytics/model", headers=h).status_code == 200
    logs = client.get("/api/audit", headers=login(client, None, "region.admin")).json()
    assert any(row["action"] == "login" for row in logs)


def test_llm_summary_endpoint_template_and_cache(client):
    _, preg = demo("QQR-NUK-DEMO2")
    h = login(client, NUK, "specialist")
    r1 = client.get(f"/api/llm/summary/{preg}", headers=h)
    assert r1.status_code == 200, r1.text
    body = r1.json()
    assert body["source"] == "template" and body["summary_uz"] and body["disclaimer_uz"]
    r2 = client.get(f"/api/llm/summary/{preg}", headers=h).json()
    assert r2["generated_at"] == body["generated_at"]  # served from cache
    assert client.get(f"/api/llm/summary/{preg}", headers=login(client, CHL, "specialist")).status_code == 404


def test_patient_without_pregnancy_returns_404_not_500(client):
    from app.models import Patient

    src_id, _ = demo("QQR-NUK-DEMO3")
    with SessionLocal() as db:
        src = db.get(Patient, src_id)
        p = Patient(code="QQR-NUK-NOPREG", full_name_enc=src.full_name_enc, pinfl_enc=src.pinfl_enc,
                    phone_enc=src.phone_enc, home_enc=src.home_enc, birth_date=src.birth_date,
                    polyclinic_id=src.polyclinic_id, mahalla_id=src.mahalla_id,
                    distance_to_perinatal_km=src.distance_to_perinatal_km, assigned_nurse_id=src.assigned_nurse_id)
        db.add(p)
        db.commit()
        pid = p.id
    r = client.get(f"/api/patients/{pid}", headers=login(client, NUK, "doctor"))
    assert r.status_code == 404 and r.json()["detail"] == "Faol homiladorlik topilmadi"
    # another polyclinic still gets the generic tenant 404, not this message
    other = client.get(f"/api/patients/{pid}", headers=login(client, CHL, "doctor"))
    assert other.status_code == 404 and other.json()["detail"] != "Faol homiladorlik topilmadi"
    with SessionLocal() as db:
        assert db.query(AuditLog).filter_by(action="view_patient", entity_id=pid).count() == 1
    # a delivered-only patient (DEMO4) still opens: the card shows the newborn
    d4, _ = demo("QQR-NUK-DEMO4")
    assert client.get(f"/api/patients/{d4}", headers=login(client, NUK, "doctor")).status_code == 200
