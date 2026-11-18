"""Task 07 parts B + C: 3-bullet doctor summary in the alert, Telegram text, escalation to the department head."""
import json
from datetime import date, timedelta

import pytest

from app.db import SessionLocal
from app.llm import summary as S
from app.llm.safety import BULLET_MAX_CHARS, validate_bullets
from app.models import Alert, AlertEvent, AuditLog, LlmSummaryCache, Patient, Polyclinic, Pregnancy, User, utcnow
from app.scheduler import escalation_job
from app.security.crypto import decrypt
from app.services import notify
from tests.conftest import CHL, NUK, demo, login
from tests.test_llm import BULLETS, PII, _fake_client, _FakeResp, payload

DEMO1_RED_VISIT = {"systolic": 152, "diastolic": 98, "proteinuria": "+2", "hemoglobin_g_l": 103,
                   "symptoms": ["severe_headache"]}


def _resp(obj: dict, parsed: bool = True):
    text = json.dumps(obj, ensure_ascii=False)
    try:
        p = S.LlmOutput.model_validate_json(text) if parsed else None
    except Exception:  # invalid output: the SDK leaves .parsed empty
        p = None
    return _FakeResp(text, p)


def _good(bullets=BULLETS):
    return {"summary_uz": "Xavf belgisi.", "key_concerns": [{"code": "R02", "text_uz": "AB"}],
            "recommended_action_codes": ["A01", "A03"], "questions_to_ask_patient_uz": ["Bosh og'riyaptimi?"],
            "doctor_bullets_uz": bullets}


@pytest.fixture(autouse=True)
def _fresh_status(monkeypatch):
    monkeypatch.setattr(S, "_STATUS", dict(S._STATUS))


# ---------------- Part B: bullets ----------------
def test_gemini_three_bullets_parsed_and_step_pinned_to_catalog(monkeypatch):
    _fake_client(monkeypatch, [_resp(_good())])
    res, _, _ = S.generate_summary(payload())
    assert res["source"] == "ai" and len(res["doctor_bullets_uz"]) == 3
    assert res["doctor_bullets_uz"][:2] == BULLETS[:2]
    assert res["doctor_bullets_uz"][2].startswith("Keyingi qadam: Perinatal markazga shoshilinch yo'llash")
    assert res["version"] == S.SUMMARY_VERSION


@pytest.mark.parametrize("bad", [BULLETS[:2], BULLETS + ["to'rtinchi"], ["", BULLETS[1], BULLETS[2]],
                                 ["x" * (BULLET_MAX_CHARS + 1), BULLETS[1], BULLETS[2]],
                                 ["Tashxis: preeklampsiya", BULLETS[1], BULLETS[2]],
                                 ["Tel +998901234567", BULLETS[1], BULLETS[2]],
                                 ["JShShIR 41234567890123", BULLETS[1], BULLETS[2]]])
def test_invalid_bullets_retry_then_template(monkeypatch, bad):
    models = _fake_client(monkeypatch, [_resp(_good(bad)), _resp(_good(bad), parsed=False)])
    res, _, _ = S.generate_summary(payload())
    assert len(models.calls) == 2  # structured -> plain retry
    assert res["source"] == "template" and len(res["doctor_bullets_uz"]) == 3


def test_wrong_count_then_good_plain_retry(monkeypatch):
    models = _fake_client(monkeypatch, [_resp(_good(BULLETS[:2])), _resp(_good(), parsed=False)])
    res, _, _ = S.generate_summary(payload())
    assert res["source"] == "ai" and len(models.calls) == 2 and len(res["doctor_bullets_uz"]) == 3


def test_template_gives_three_valid_bullets():
    res = S.template_summary(payload())
    b = res["doctor_bullets_uz"]
    assert validate_bullets(b) == b and len(b) == 3
    assert b[0].startswith("QIZIL zona:") and "Preeklampsiya" in b[0]
    assert "152/98" in b[1] and b[2].startswith("Keyingi qadam:")


def test_template_bullets_use_trend_series():
    p = payload()
    p["zone"], p["rule_hits"] = "yellow", []
    p["trend_hits"] = [{"code": "P01", "zone": "yellow", "text": "Diastolik bosim 3 ko'rikda ketma-ket oshmoqda",
                        "param": "diastolic", "values": [72, 78, 84], "weeks": [25.3, 27.3, 29.3], "unit": "mmHg"}]
    b = S.template_summary(p)["doctor_bullets_uz"]
    assert b[0].startswith("SARIQ zona: Diastolik")
    assert "72 (25.3 hf) → 78 (27.3 hf) → 84 (29.3 hf)" in b[1]
    assert all(len(x) <= BULLET_MAX_CHARS for x in b)


def test_payload_has_trend_series_but_no_pii_or_dates():
    from tests.test_llm import ASSESSMENT, PREG, VISITS

    assessment = {**ASSESSMENT, "trend_hits": [{"code": "P01", "zone": "red", "uz_text": "x", "kind": "trend",
                                                "param": "systolic", "values": [116, 125, 134], "weeks": [24, 27, 30],
                                                "dates": ["2026-10-01", "2026-10-22", "2026-11-12"]}]}
    p = S.build_llm_input("QQR-NUK-DEMO1", date(2007, 1, 1), PREG, VISITS, assessment)
    text = json.dumps(p, ensure_ascii=False, default=str)
    assert p["trend_hits"][0]["values"] == [116, 125, 134] and "dates" not in p["trend_hits"][0]
    assert "2026-10-01" not in text
    for value in PII.values():
        assert value not in text
    bullets = S.template_summary(p)["doctor_bullets_uz"]
    for value in PII.values():
        assert all(value not in b for b in bullets)


def test_old_cache_version_is_regenerated(client):
    from app.services import ai_summary as A
    from app.services.scoring import latest_assessment

    _, preg = demo("QQR-NUK-DEMO3")
    with SessionLocal() as db:
        ra = latest_assessment(db, preg)
        A.build_and_store(db, ra)
        row = db.query(LlmSummaryCache).filter_by(risk_assessment_id=ra.id).one()
        row.payload = {k: v for k, v in row.payload.items() if k not in ("version", "doctor_bullets_uz")}
        db.commit()
        assert A.get_cached(db, ra.id) is None  # v1 row -> treated as missing
    body = client.get(f"/api/llm/summary/{preg}", headers=login(client, NUK, "specialist")).json()
    assert body["status"] == "ready" and len(body["doctor_bullets_uz"]) == 3


# ---------------- Part B: alert + Telegram ----------------
def _red_alert(client, code="QQR-NUK-DEMO1", visit=None):
    _, preg = demo(code)
    r = client.post("/api/visits", json={"pregnancy_id": preg, **(visit or DEMO1_RED_VISIT)},
                    headers=login(client, NUK, "nurse"))
    assert r.status_code == 201, r.text
    return r.json()["alert"]


def test_alert_carries_three_bullets_and_telegram_is_deidentified(client):
    client.app.state.scheduler.pause()
    notify.OUTBOX.clear()
    alert = _red_alert(client)
    assert alert["level"] == "red"
    h = login(client, NUK, "specialist")
    a = next(x for x in client.get("/api/alerts?status=active", headers=h).json() if x["id"] == alert["id"])
    assert a["summary_status"] == "ready" and a["summary_source"] == "template" and len(a["summary_bullets"]) == 3
    assert a["history"][0]["event"] == "created" and a["history"][0]["assignee_role"] == "specialist"
    msgs = [m for m in notify.OUTBOX if m["alert_id"] == alert["id"] and m["kind"] == "new_alert"]
    assert len(msgs) == 1 and msgs[0]["role"] == "specialist" and msgs[0]["status"] == "offline"
    text = msgs[0]["text"]
    assert "QQR-NUK-DEMO1" in text and all(f"• {b}" in text for b in a["summary_bullets"])
    assert "Yakuniy qaror shifokorga tegishli" in text
    with SessionLocal() as db:
        pat = db.query(Patient).filter_by(code="QQR-NUK-DEMO1").one()
        for secret in (decrypt(pat.full_name_enc), decrypt(pat.pinfl_enc), decrypt(pat.phone_enc), pat.mahalla.name):
            assert secret not in text
    client.app.state.scheduler.resume()


def test_alert_summary_pending_when_gemini_is_slow(client, monkeypatch):
    from app.api import alerts as alerts_api

    real = alerts_api.get_settings()
    monkeypatch.setattr(alerts_api, "get_settings", lambda: real.model_copy(update={"gemini_api_key": "fake"}))
    monkeypatch.setattr(alerts_api, "generate_cached", lambda ra_id: None)  # never finishes
    with SessionLocal() as db:
        a = (db.query(Alert).join(Pregnancy, Alert.pregnancy_id == Pregnancy.id).join(Patient)
             .join(Polyclinic).filter(Polyclinic.code == NUK, Alert.status.in_(("open", "escalated"))).first())
        db.query(LlmSummaryCache).filter_by(risk_assessment_id=a.risk_assessment_id).delete()
        db.commit()
        aid = a.id
    rows = client.get("/api/alerts?status=active", headers=login(client, NUK, "specialist")).json()
    row = next(x for x in rows if x["id"] == aid)
    assert row["summary_status"] == "pending" and row["summary_bullets"] is None


def test_trend_driven_alert_is_marked(client):
    rows = client.get("/api/alerts", headers=login(client, NUK, "specialist")).json()
    trnd = [r for r in rows if r["patient_code"] == "QQR-NUK-TRND2"]
    assert trnd and trnd[0]["trend_driven"] is True
    assert not any(r["trend_driven"] for r in rows if r["patient_code"] == "QQR-NUK-DEMO2")


# ---------------- Part C: department head ----------------
def _overdue(aid: int) -> None:
    with SessionLocal() as db:
        db.get(Alert, aid).sla_due_at = utcnow() - timedelta(minutes=1)
        db.commit()


def test_department_head_logs_in_and_sees_only_own_polyclinic(client):
    h = login(client, NUK, "department_head")
    me = client.get("/api/auth/me", headers=h).json()
    assert me["role"] == "department_head" and me["polyclinic_code"] == NUK
    rows = client.get("/api/alerts", headers=h).json()
    assert rows and all(r["patient_code"].removeprefix("B-").startswith("QQR-NUK-") for r in rows)  # child: B-<mother>
    other = login(client, CHL, "department_head")
    for path, body in ((f"/api/alerts/{rows[0]['id']}/ack", {"action_taken": "boshqa"}),
                       (f"/api/alerts/{rows[0]['id']}/reassign", {"user_id": 1})):
        assert client.post(path, json=body, headers=other).status_code == 404
    assert client.get(f"/api/patients/{rows[0]['patient_id']}", headers=other).status_code == 404
    assert client.get("/api/geo/country", headers=h).status_code == 403  # admin aggregates: not for staff


def test_overdue_red_goes_to_department_head_then_district_admin_count(client):
    client.app.state.scheduler.pause()
    notify.OUTBOX.clear()
    aid = _red_alert(client, "QQR-NUK-DEMO3", {"systolic": 166, "diastolic": 112})["id"]
    _overdue(aid)
    assert escalation_job() >= 1
    head = login(client, NUK, "department_head")
    late = client.get("/api/alerts?status=active&mine=true&escalated=true", headers=head).json()
    a = next(x for x in late if x["id"] == aid)
    assert a["status"] == "escalated" and a["escalation_level"] == 1 and a["assigned_role"] == "department_head"
    assert [e["event"] for e in a["history"]] == ["created", "escalated"]
    assert a["next_role"] == "district_admin"
    assert any(m["alert_id"] == aid and m["kind"] == "escalated" and m["role"] == "department_head"
               for m in notify.OUTBOX)
    # second SLA period -> district admin is notified with a COUNT only; the patient stays with the department head
    _overdue(aid)
    assert escalation_job() >= 1
    with SessionLocal() as db:
        al = db.get(Alert, aid)
        assert al.escalation_level == 2
        assert db.query(AlertEvent).filter_by(alert_id=aid, event="admin_notified").count() == 1
        assert db.query(AuditLog).filter_by(action="escalate_alert_l2", entity_id=aid).count() == 1
        code = al.pregnancy.patient.code
    a = next(x for x in client.get("/api/alerts?status=active", headers=head).json() if x["id"] == aid)
    assert a["assigned_role"] == "department_head"
    admin_msgs = [m for m in notify.OUTBOX if m["alert_id"] == aid and m["kind"] == "admin_count"]
    assert len(admin_msgs) == 1 and admin_msgs[0]["role"] == "district_admin"
    assert code not in admin_msgs[0]["text"] and "•" not in admin_msgs[0]["text"]
    assert client.get("/api/alerts", headers=login(client, None, "district.admin")).status_code == 403
    _overdue(aid)
    escalation_job()
    with SessionLocal() as db:
        assert db.get(Alert, aid).escalation_level == 2  # end of the chain
    client.app.state.scheduler.resume()


def test_acknowledged_before_deadline_is_not_escalated(client):
    client.app.state.scheduler.pause()
    aid = _red_alert(client, "QQR-NUK-DEMO2", {"systolic": 165, "diastolic": 112})["id"]
    spec = login(client, NUK, "specialist")
    assert client.post(f"/api/alerts/{aid}/ack", json={"action_taken": "Bog'lanildi"}, headers=spec).status_code == 200
    _overdue(aid)
    escalation_job()
    with SessionLocal() as db:
        a = db.get(Alert, aid)
        assert a.escalation_level == 0 and a.status == "acknowledged"
    client.app.state.scheduler.resume()


def test_demo_button_escalates_to_department_head_who_acknowledges(client):
    client.app.state.scheduler.pause()
    _, preg = demo("QQR-NUK-TRND1")
    r = client.post("/api/visits", json={"pregnancy_id": preg, "systolic": 168, "diastolic": 112},
                    headers=login(client, NUK, "nurse")).json()
    aid = r["alert"]["id"]
    spec = login(client, NUK, "specialist")
    assert client.post(f"/api/alerts/{aid}/demo-expire-sla", headers=spec).status_code == 200
    assert escalation_job() >= 1
    head = login(client, NUK, "department_head")
    late = client.get("/api/alerts?status=active&mine=true&escalated=true", headers=head).json()
    assert aid in {x["id"] for x in late}
    ok = client.post(f"/api/alerts/{aid}/ack", json={"action_taken": "Perinatal markazga yo'llandi"}, headers=head)
    assert ok.status_code == 200 and ok.json()["status"] == "acknowledged"
    assert [e["event"] for e in ok.json()["history"]][-1] == "acknowledged"
    with SessionLocal() as db:
        assert db.query(AuditLog).filter_by(action="ack_alert", entity_id=aid).count() == 1
    client.app.state.scheduler.resume()


def test_department_head_reassigns_to_specialist(client):
    client.app.state.scheduler.pause()
    aid = _red_alert(client, "QQR-NUK-TRND3", {"systolic": 170, "diastolic": 112})["id"]
    _overdue(aid)
    escalation_job()
    head = login(client, NUK, "department_head")
    specs = client.get("/api/alerts/assignees", headers=head).json()
    assert len(specs) == 1 and "mutaxassisi" in specs[0]["full_name"]
    assert client.get("/api/alerts/assignees", headers=login(client, NUK, "specialist")).status_code == 403
    notify.OUTBOX.clear()
    r = client.post(f"/api/alerts/{aid}/reassign", json={"user_id": specs[0]["id"], "note": "Darhol ko'ring"},
                    headers=head)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["assigned_role"] == "specialist" and body["history"][-1]["event"] == "reassigned"
    assert any(m["kind"] == "reassigned" and m["role"] == "specialist" for m in notify.OUTBOX)
    with SessionLocal() as db:
        assert db.query(AuditLog).filter_by(action="reassign_alert", entity_id=aid).count() == 1
        chl = db.query(Polyclinic).filter_by(code=CHL).one()
        other = db.query(User).filter_by(role="specialist", polyclinic_id=chl.id).one().id
    assert client.post(f"/api/alerts/{aid}/reassign", json={"user_id": other}, headers=head).status_code == 404
    assert client.post(f"/api/alerts/{aid}/reassign", json={"user_id": specs[0]["id"]},
                       headers=login(client, NUK, "specialist")).status_code == 403
    client.app.state.scheduler.resume()


def test_yellow_chain_unchanged_goes_to_doctor(client):
    from app.services.alerts import ESCALATION_CHAIN, chain_role

    assert ESCALATION_CHAIN["yellow"][1] == "doctor" and chain_role("red", 1) == "department_head"
    assert chain_role("red", 2) == chain_role("yellow", 2) == "district_admin"


def test_sla_settings_read_only_for_head_and_admins(client):
    for who in (login(client, NUK, "department_head"), login(client, None, "district.admin")):
        r = client.get("/api/settings/sla", headers=who)
        assert r.status_code == 200
        body = r.json()
        assert body["sla_red_minutes"] == 120 and body["effective_sla_red_minutes"] == 10
        assert body["chain"]["red"] == ["specialist", "department_head", "district_admin"]
    assert client.get("/api/settings/sla", headers=login(client, NUK, "specialist")).status_code == 403
