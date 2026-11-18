"""Children 0-12 months end to end: list/card, check + live preview, child alerts (3 bullets, escalation, Telegram),
tenancy, the subject switch on dashboard / alerts / map / admin aggregates, privacy of the child LLM payload."""
from datetime import timedelta

import pytest
from sqlalchemy import select

from tests.conftest import CHL, NUK, login

DEMO4_CHILD, DEMO5_CHILD = "B-QQR-NUK-DEMO4-1", "B-QQR-NUK-DEMO5-1"


def _child(code: str):
    from app.db import SessionLocal
    from app.models import Newborn

    with SessionLocal() as db:
        return db.scalars(select(Newborn).where(Newborn.code == code)).one()


def test_children_list_and_tenant_keys(client):
    rows = client.get("/api/children", headers=login(client, NUK, "nurse")).json()
    assert len(rows) >= 6 and all(r["code"].startswith("B-QQR-NUK-") for r in rows)
    assert all(0 <= r["age_days"] <= 365 for r in rows)
    demo4 = next(r for r in rows if r["code"] == DEMO4_CHILD)
    assert demo4["zone"] == "red" and demo4["mother_code"] == "QQR-NUK-DEMO4" and demo4["main_reason"]
    assert rows[0]["zone"] == "red"  # red first
    from app.db import SessionLocal
    from app.models import Newborn

    with SessionLocal() as db:  # tenant key copied from the mother's patient record
        for nb in db.scalars(select(Newborn)).all():
            assert nb.polyclinic_id == nb.pregnancy.patient.polyclinic_id
            assert nb.mahalla_id == nb.pregnancy.patient.mahalla_id
            assert nb.code == f"B-{nb.pregnancy.patient.code}-1" and nb.sex in ("m", "f")
            assert 2 <= len(nb.checks) <= 6


def test_child_card(client):
    nb = _child(DEMO5_CHILD)
    h = login(client, NUK, "doctor")
    d = client.get(f"/api/children/{nb.id}", headers=h).json()
    assert d["code"] == DEMO5_CHILD and d["zone"] == "green" and d["mother_code"] == "QQR-NUK-DEMO5"
    assert d["latest_assessment"]["ml_probability"] is None
    assert "faqat klinik qoidalar va trendlar" in d["latest_assessment"]["explanation_uz"]
    assert len(d["checks"]) == 6 and d["checks"][-1]["age_days"] == 122
    assert len(d["reference"]) == 13 and d["reference"][6]["median"] == 7.9  # WHO boys, 6 months
    assert d["growth"][0]["age_months"] == 0 and all(p["z"] is not None for p in d["growth"])
    st = {v["code"]: v["status"] for v in d["vaccines"]}
    assert st["BCG"] == "given" and st["Penta-3"] == "given" and st["MMR-1"] == "upcoming"
    from app.db import SessionLocal
    from app.models import AuditLog

    with SessionLocal() as db:
        assert db.scalars(select(AuditLog).where(AuditLog.action == "view_child", AuditLog.entity_id == nb.id)).first()
    # the mother's card lists her child
    mother = client.get(f"/api/patients/{d['mother_patient_id']}", headers=h).json()
    kid = next(k for k in mother["newborns"] if k["code"] == DEMO5_CHILD)
    assert kid["id"] == nb.id and kid["age_days"] == d["age_days"] and kid["sex"] == "m"


def test_preview_uses_age_dependent_breathing_and_saves_nothing(client):
    nb = _child(DEMO5_CHILD)
    h = login(client, NUK, "nurse")
    r = client.post("/api/children/risk/preview", headers=h, json={"newborn_id": nb.id, "resp_rate": 56, "weight_g": 7300})
    assert r.status_code == 200
    res = r.json()
    assert res["zone"] == "red" and "I05" in {x["code"] for x in res["rule_hits"]}
    assert client.get(f"/api/children/{nb.id}", headers=h).json()["zone"] == "green"  # nothing saved


def test_red_child_check_creates_alert_with_three_bullets(client):
    from app.services import notify

    nb = _child(DEMO5_CHILD)
    h = login(client, NUK, "nurse")
    r = client.post("/api/children/checks", headers=h, json={
        "newborn_id": nb.id, "resp_rate": 56, "temperature_c": 37.4, "weight_g": 7300, "cough_days": 3,
        "feeding": "exclusive_breast", "notes": "Ona: Zarina Qodirova, +998901234567"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["previous_zone"] == "green" and body["assessment"]["zone"] == "red"
    a = body["alert"]
    assert a["subject"] == "child" and a["newborn_id"] == nb.id and a["pregnancy_id"] is None
    assert a["patient_code"] == DEMO5_CHILD and a["subject_label"] == "Bola · 4 oy" and a["level"] == "red"
    assert a["assigned_role"] == "specialist"
    assert body["check"]["age_days"] == 125 and body["check"]["vaccines_due_overdue"] == []

    hs = login(client, NUK, "specialist")
    rows = client.get("/api/alerts?status=active&subject=child", headers=hs).json()
    mine = next(x for x in rows if x["id"] == a["id"])
    assert mine["summary_status"] == "ready" and mine["summary_source"] == "template"
    assert len(mine["summary_bullets"]) == 3 and "I05" not in mine["summary_bullets"][0]
    assert "tez nafas" in mine["summary_bullets"][0].lower() and "oy" in mine["summary_bullets"][1]
    assert mine["summary_bullets"][2].startswith("Keyingi qadam: Bolani shoshilinch")
    assert all(x["subject"] == "child" for x in rows)
    assert all(x["subject"] == "pregnancy" for x in client.get("/api/alerts?subject=pregnancy", headers=hs).json())

    msg = next(m for m in reversed(notify.OUTBOX) if m["alert_id"] == a["id"] and m["kind"] == "new_alert")
    assert f"Bola kodi: {DEMO5_CHILD} · 4 oy" in msg["text"]
    for leak in ("Zarina", "Qodirova", "+998", "QQR-NUK-DEMO5 "):
        assert leak not in msg["text"]


def test_child_alert_escalates_to_department_head_then_district_count(client):
    from app.db import SessionLocal
    from app.models import Alert, utcnow
    from app.services import notify
    from app.services.alerts import run_escalations

    nb = _child(DEMO5_CHILD)
    with SessionLocal() as db:
        a = db.scalars(select(Alert).where(Alert.newborn_id == nb.id, Alert.status == "open")).first()
        assert a is not None
        alert_id = a.id
        a.sla_due_at = utcnow() - timedelta(seconds=1)
        db.commit()
        assert run_escalations(db) >= 1
        db.refresh(a)
        assert a.escalation_level == 1 and a.status == "escalated"
        a.sla_due_at = utcnow() - timedelta(seconds=1)
        db.commit()
        run_escalations(db)
        db.refresh(a)
        assert a.escalation_level == 2
    head = login(client, NUK, "department_head")
    late = client.get("/api/alerts?status=active&mine=true&escalated=true", headers=head).json()
    row = next(x for x in late if x["id"] == alert_id)
    assert row["assigned_role"] == "department_head" and [e["event"] for e in row["history"]][:3] == \
        ["created", "escalated", "admin_notified"]
    admin_msg = next(m for m in reversed(notify.OUTBOX) if m["alert_id"] == alert_id and m["kind"] == "admin_count")
    assert DEMO5_CHILD not in admin_msg["text"] and "soni" in admin_msg["text"]
    r = client.post(f"/api/alerts/{alert_id}/ack", headers=head, json={"action_taken": "Bola shifoxonaga yo'llandi"})
    assert r.status_code == 200 and r.json()["status"] == "acknowledged"


def test_child_ai_summary_endpoint(client):
    nb = _child(DEMO4_CHILD)
    r = client.get(f"/api/llm/summary/child/{nb.id}", headers=login(client, NUK, "specialist"))
    assert r.status_code == 200
    s = r.json()
    assert s["status"] == "ready" and s["source"] == "template" and len(s["doctor_bullets_uz"]) == 3
    assert "ML modeli qo'llanilmaydi" in s["summary_uz"]
    assert {a["code"] for a in s["recommended_actions"]} & {"A21", "A28"}


def test_child_llm_payload_is_allow_listed(client):
    from app.db import SessionLocal
    from app.services.ai_summary import llm_payload
    from app.services.children import latest_child_assessment

    nb = _child(DEMO4_CHILD)
    with SessionLocal() as db:
        p = llm_payload(db, latest_child_assessment(db, nb.id))
    assert set(p) == {"subject", "patient_code", "age_months", "sex", "last_checks", "zone", "ml_probability",
                      "rule_hits", "trend_hits", "shap_top"}
    assert p["subject"] == "child" and p["patient_code"] == DEMO4_CHILD and p["sex"] == "qiz"
    flat = str(p)
    for bad in ("Shahnoza", "Ergasheva", "check_date", "birth_date", "notes", "home", "pinfl", "phone", "+998"):
        assert bad not in flat
    assert all("age_months" in c and "check_date" not in c for c in p["last_checks"])


def test_other_tenant_cannot_reach_children(client):
    nb = _child(DEMO4_CHILD)
    from app.db import SessionLocal
    from app.models import Alert

    with SessionLocal() as db:
        alert_id = db.scalars(select(Alert.id).where(Alert.newborn_id == nb.id)).first()
    h = login(client, CHL, "doctor")
    for method, path, body in [("GET", f"/api/children/{nb.id}", None),
                               ("POST", "/api/children/risk/preview", {"newborn_id": nb.id, "resp_rate": 40}),
                               ("POST", "/api/children/checks", {"newborn_id": nb.id, "resp_rate": 40}),
                               ("GET", f"/api/llm/summary/child/{nb.id}", None),
                               ("POST", f"/api/alerts/{alert_id}/resolve", {"action_taken": "boshqa poliklinika"})]:
        r = client.request(method, path, json=body, headers=h)
        assert r.status_code == 404, (path, r.status_code)
    assert all(not r["code"].startswith("B-QQR") for r in client.get("/api/children", headers=h).json())
    admin = login(client, None, "region.admin")
    assert client.get("/api/children", headers=admin).status_code == 403
    assert client.get(f"/api/children/{nb.id}", headers=admin).status_code == 403


def test_subject_switch_counts_dashboard_and_map(client):
    h = login(client, NUK, "doctor")
    preg = client.get("/api/dashboard/summary", headers=h).json()
    kids = client.get("/api/dashboard/summary?subject=child", headers=h).json()
    both = client.get("/api/dashboard/summary?subject=all", headers=h).json()
    assert preg["counts"] == kids["counts"] == both["counts"]
    assert kids["active"] == kids["red"] + kids["yellow"] + kids["green"] == preg["counts"]["child"]
    assert both["active"] == preg["active"] + kids["active"]
    assert client.get("/api/dashboard/summary?subject=x", headers=h).status_code == 422
    top = client.get("/api/dashboard/top?subject=child", headers=h).json()
    assert top and all(r["subject"] == "child" and r["risk"] is None and r["child_age_days"] is not None for r in top)
    assert len(client.get("/api/dashboard/trend?subject=child", headers=h).json()) == 13
    pts = client.get("/api/polyclinic/map", headers=h).json()["points"]
    child_pts = [p for p in pts if p["kind"] == "child"]
    assert len(child_pts) == preg["counts"]["child"] and all(p["newborn_id"] for p in child_pts)
    assert len(pts) - len(child_pts) == preg["counts"]["pregnancy"]


def test_admin_aggregates_have_the_switch(client):
    h = login(client, None, "district.admin")
    from app.db import SessionLocal
    from app.models import Polyclinic

    with SessionLocal() as db:
        pc = db.scalars(select(Polyclinic).where(Polyclinic.code == NUK)).one()
    preg = client.get(f"/api/geo/polyclinics/{pc.id}", headers=h).json()
    kids = client.get(f"/api/geo/polyclinics/{pc.id}?subject=child", headers=h).json()
    both = client.get(f"/api/geo/polyclinics/{pc.id}?subject=all", headers=h).json()
    assert kids["total"] == kids["subject_counts"]["child"] > 0 and preg["total"] == preg["subject_counts"]["pregnancy"]
    assert both["total"] == preg["total"] + kids["total"]
    dist = client.get(f"/api/geo/districts/{pc.district_id}?subject=child", headers=h).json()
    assert dist["subject_counts"]["child"] == kids["total"]
    flat = str(kids) + str(dist)
    assert "B-QQR" not in flat and "QQR-NUK-" not in flat  # counts only


def test_alert_has_exactly_one_subject(client):
    from sqlalchemy.exc import IntegrityError

    from app.db import SessionLocal
    from app.models import Alert, RiskAssessment, utcnow

    with SessionLocal() as db:
        ra_id = db.scalars(select(RiskAssessment.id)).first()
        db.add(Alert(risk_assessment_id=ra_id, level="red", sla_due_at=utcnow()))
        with pytest.raises(IntegrityError):
            db.flush()


def test_ensure_columns_adds_missing_columns(tmp_path):
    from sqlalchemy import create_engine, inspect, text

    from app.db import ensure_columns

    eng = create_engine(f"sqlite:///{(tmp_path / 'old.db').as_posix()}")
    with eng.begin() as conn:  # an old-schema newborns table (before task 08)
        conn.execute(text("CREATE TABLE newborns (id INTEGER PRIMARY KEY, pregnancy_id INTEGER, birth_date DATE, "
                          "gestational_weeks_at_birth FLOAT, birth_weight_g INTEGER, apgar_5 INTEGER, current_zone VARCHAR(8))"))
        conn.execute(text("INSERT INTO newborns VALUES (1, 1, '2026-01-01', 39, 3300, 9, 'green')"))
    added = ensure_columns(eng)
    assert {"newborns.sex", "newborns.code", "newborns.polyclinic_id"} <= set(added)
    cols = {c["name"] for c in inspect(eng).get_columns("newborns")}
    assert {"sex", "status", "current_risk_score", "mahalla_id"} <= cols
    with eng.connect() as conn:
        assert conn.execute(text("SELECT birth_weight_g FROM newborns")).scalar() == 3300  # data kept
    assert ensure_columns(eng) == []
