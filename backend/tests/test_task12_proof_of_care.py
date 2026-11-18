"""Task 12: proof of care — closed loop, two-person rule, reopen, unreachable workflow, quality signals."""
from datetime import timedelta

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Alert, AuditLog, Patient, Pregnancy, User, utcnow
from app.services.alerts import run_escalations
from tests.conftest import CHL, FRG, NUK, SAM, login

RED_VISIT = {"systolic": 152, "diastolic": 98, "proteinuria": "+2", "symptoms": ["severe_headache"],
             "hemoglobin_g_l": 118, "weight_kg": 66.4}
STILL_RED = {"systolic": 166, "diastolic": 112, "proteinuria": "+2", "hemoglobin_g_l": 118, "weight_kg": 66.5}
CALM = {"systolic": 118, "diastolic": 76, "proteinuria": "neg", "hemoglobin_g_l": 121, "weight_kg": 66.5}
_used: set[int] = set()


def _green_pregnancy(code: str = NUK) -> tuple[int, int]:
    """An active GREEN pregnancy of this polyclinic not used by an earlier test in this module."""
    from app.models import Polyclinic

    with SessionLocal() as db:
        pc = db.scalars(select(Polyclinic).where(Polyclinic.code == code)).one()
        rows = db.execute(select(Patient.id, Pregnancy.id).join(Pregnancy, Pregnancy.patient_id == Patient.id)
                          .where(Patient.polyclinic_id == pc.id, Pregnancy.status == "active",
                                 Pregnancy.current_zone == "green", Patient.code.not_like("%DEMO%"))
                          .order_by(Pregnancy.id)).all()
    pid, preg = next((p, g) for p, g in rows if g not in _used)
    _used.add(preg)
    return pid, preg


def _visit(client, preg, body, h):
    r = client.post("/api/visits", json={"pregnancy_id": preg, **body}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def _new_red_alert(client, code: str = NUK) -> tuple[int, int, dict]:
    pid, preg = _green_pregnancy(code)
    body = _visit(client, preg, RED_VISIT, login(client, code, "nurse"))
    assert body["assessment"]["zone"] == "red" and body["alert"], body["assessment"]["zone"]
    return pid, preg, body["alert"]


def _uid(code: str, username: str) -> int:
    from app.models import Polyclinic

    with SessionLocal() as db:
        pc = db.scalars(select(Polyclinic).where(Polyclinic.code == code)).one()
        return db.scalars(select(User.id).where(User.polyclinic_id == pc.id, User.username == username)).one()


RESOLVE = {"action_codes": ["A02", "A10"], "outcome": "improved", "note": "Bosim me'yorlashdi"}


# ---------------- Part A + C ----------------
def test_closure_blocked_without_new_measurement_then_two_person_confirm(client):
    _, preg, alert = _new_red_alert(client)
    aid = alert["id"]
    spec, nurse, doc = login(client, NUK, "specialist"), login(client, NUK, "nurse"), login(client, NUK, "doctor")
    assert alert["required_measurements"] and "arterial bosim (sistolik)" in alert["required_measurements"]

    ack = client.post(f"/api/alerts/{aid}/ack", json={"action_taken": "Qo'ng'iroq qilindi"}, headers=spec).json()
    assert ack["status"] == "acknowledged" and ack["measurement_due_at"] and not ack["has_measurement"]

    r = client.post(f"/api/alerts/{aid}/resolve", json=RESOLVE, headers=spec)
    assert r.status_code == 409 and r.json()["detail"] == "Yopish uchun yangi o'lchov kerak"

    _visit(client, preg, {"weight_kg": 66.6}, nurse)  # a new visit WITHOUT blood pressure does not count
    assert client.post(f"/api/alerts/{aid}/resolve", json=RESOLVE, headers=spec).status_code == 409

    _visit(client, preg, CALM, nurse)
    assert client.post(f"/api/alerts/{aid}/resolve", json={**RESOLVE, "action_codes": ["X99"]}, headers=spec).status_code == 422
    assert client.post(f"/api/alerts/{aid}/resolve", json={**RESOLVE, "outcome": "ok"}, headers=spec).status_code == 422
    assert client.post(f"/api/alerts/{aid}/resolve", json={**RESOLVE, "action_codes": []}, headers=spec).status_code == 422

    res = client.post(f"/api/alerts/{aid}/resolve", json=RESOLVE, headers=spec).json()
    assert res["status"] == "pending_confirmation" and res["has_measurement"]
    assert res["resolution_outcome"] == "improved" and [a["code"] for a in res["resolution_actions"]] == ["A02", "A10"]
    assert res["resolved_by_user_id"] == _uid(NUK, "specialist")

    assert client.post(f"/api/alerts/{aid}/confirm", json={}, headers=spec).status_code == 403  # role
    ok = client.post(f"/api/alerts/{aid}/confirm", json={"approve": True}, headers=doc).json()
    assert ok["status"] == "resolved" and ok["confirmed_by"] and ok["confirmed_at"]
    events = [e["event"] for e in ok["history"]]
    assert "resolution_proposed" in events and events[-1] == "resolved" and "measured" in events
    with SessionLocal() as db:
        acts = set(db.scalars(select(AuditLog.action).where(AuditLog.entity == "alert", AuditLog.entity_id == aid)).all())
    assert {"propose_resolution", "confirm_closure"} <= acts


def test_same_user_cannot_resolve_and_confirm(client):
    _, preg, alert = _new_red_alert(client)
    aid = alert["id"]
    doc, head = login(client, NUK, "doctor"), login(client, NUK, "department_head")
    client.post(f"/api/alerts/{aid}/ack", json={"action_taken": "Ko'rikka chaqirildi"}, headers=doc)
    _visit(client, preg, CALM, login(client, NUK, "nurse"))
    assert client.post(f"/api/alerts/{aid}/resolve", json=RESOLVE, headers=doc).json()["status"] == "pending_confirmation"
    r = client.post(f"/api/alerts/{aid}/confirm", json={"approve": True}, headers=doc)
    assert r.status_code == 409 and "boshqa xodim" in r.json()["detail"]
    # returning the closure sends it back (still needs closure); then a different user can confirm a new proposal
    back = client.post(f"/api/alerts/{aid}/confirm", json={"approve": False, "note": "Qayta ko'ring"}, headers=head).json()
    assert back["status"] == "acknowledged"
    client.post(f"/api/alerts/{aid}/resolve", json=RESOLVE, headers=doc)
    assert client.post(f"/api/alerts/{aid}/confirm", json={}, headers=head).json()["status"] == "resolved"


def test_yellow_closure_needs_measurement_but_no_second_person(client):
    _, preg = _green_pregnancy()
    nurse, spec = login(client, NUK, "nurse"), login(client, NUK, "specialist")
    body = _visit(client, preg, {"systolic": 145, "diastolic": 92, "proteinuria": "neg", "weight_kg": 64}, nurse)
    assert body["assessment"]["zone"] == "yellow" and body["alert"]["level"] == "yellow"
    aid = body["alert"]["id"]
    assert client.post(f"/api/alerts/{aid}/resolve", json=RESOLVE, headers=spec).status_code == 409
    _visit(client, preg, CALM, nurse)
    done = client.post(f"/api/alerts/{aid}/resolve", json=RESOLVE, headers=spec).json()
    assert done["status"] == "resolved" and done["confirmed_by"] is None


# ---------------- Part B ----------------
def test_reopen_when_first_assessment_after_closure_is_still_red(client):
    _, preg, alert = _new_red_alert(client)
    aid = alert["id"]
    nurse, spec, head = login(client, NUK, "nurse"), login(client, NUK, "specialist"), login(client, NUK, "department_head")
    client.post(f"/api/alerts/{aid}/ack", json={"action_taken": "Perinatal markazga yo'llandi"}, headers=spec)
    still = _visit(client, preg, STILL_RED, nurse)
    assert still["assessment"]["zone"] == "red" and still["alert"] is None  # red -> red: no new alert
    client.post(f"/api/alerts/{aid}/resolve", json={"action_codes": ["A01"], "outcome": "referred"}, headers=spec)
    assert client.post(f"/api/alerts/{aid}/confirm", json={}, headers=head).json()["status"] == "resolved"

    again = _visit(client, preg, STILL_RED, nurse)
    assert again["assessment"]["zone"] == "red" and again["alert"] is None
    a = next(x for x in client.get("/api/alerts?status=active", headers=spec).json() if x["id"] == aid)
    assert a["status"] == "open" and a["reopened_count"] == 1 and a["history"][-1]["event"] == "reopened"
    with SessionLocal() as db:
        assert db.scalar(select(AuditLog.id).where(AuditLog.action == "reopen_alert", AuditLog.entity_id == aid))
    # a later red assessment does not reopen again (only the FIRST one after closure counts)
    assert client.get("/api/alerts?status=active", headers=spec).status_code == 200


def test_acknowledged_without_measurement_escalates_again(client):
    _, _, alert = _new_red_alert(client)
    aid = alert["id"]
    client.post(f"/api/alerts/{aid}/ack", json={"action_taken": "Qabul qildim"}, headers=login(client, NUK, "specialist"))
    with SessionLocal() as db:
        a = db.get(Alert, aid)
        a.measurement_due_at = utcnow() - timedelta(minutes=1)
        db.commit()
        run_escalations(db)
        db.refresh(a)
        assert a.status == "escalated" and a.escalation_level == 1
        assert db.get(User, a.assigned_user_id).role == "department_head"
        assert "o'lchov" in (a.events[-1].note or "")


# ---------------- Part D ----------------
def _attempt(client, aid, h, **kw):
    return client.post(f"/api/alerts/{aid}/contact-attempts", json={"channel": "phone", "result": "phone_off", **kw},
                       headers=h)


def test_unreachable_after_three_failed_attempts_over_two_days(client):
    _, _, alert = _new_red_alert(client)
    aid = alert["id"]
    with SessionLocal() as db:  # the alert is 3 days old, so attempts can be dated yesterday
        a = db.get(Alert, aid)
        a.created_at = utcnow() - timedelta(days=3)
        db.commit()
    nurse = login(client, NUK, "nurse")
    yesterday = (utcnow() - timedelta(days=1)).isoformat()
    assert _attempt(client, aid, nurse, attempted_at=yesterday).json()["status"] == "open"
    assert _attempt(client, aid, nurse, result="not_found", channel="home_visit").json()["status"] == "open"
    r = _attempt(client, aid, nurse, result="elsewhere", channel="mahalla").json()
    assert r["status"] == "unreachable" and r["failed_attempts"] == 3
    assert "3 marta" in r["unreachable_reason"] and r["escalation_level"] == 1 and r["retry_due_at"]
    assert [e["event"] for e in r["history"]][-2:] == ["unreachable", "escalated"]
    assert all(c["result_uz"] for c in r["contact_attempts"])
    # specialists cannot log attempts (nurse / doctor only); bad values are rejected
    assert _attempt(client, aid, login(client, NUK, "specialist")).status_code == 403
    assert _attempt(client, aid, nurse, channel="pigeon").status_code == 422


def test_three_attempts_on_one_day_are_not_enough(client):
    _, _, alert = _new_red_alert(client)
    nurse = login(client, NUK, "nurse")
    for _ in range(3):
        r = _attempt(client, alert["id"], nurse).json()
    assert r["status"] == "open" and r["failed_attempts"] == 3 and r["unreachable_at"] is None


def test_refusal_path_counselling_note_retry_then_measurement(client):
    _, preg, alert = _new_red_alert(client)
    aid = alert["id"]
    doc = login(client, NUK, "doctor")
    refuse = {"channel": "home_visit", "result": "refused"}
    assert _attempt(client, aid, doc, **refuse, note="Oila rozi emas, keyinroq").status_code == 422  # no checklist
    assert _attempt(client, aid, doc, **refuse, counselling=["danger_signs"]).status_code == 422  # no note
    r = _attempt(client, aid, doc, **refuse, counselling=["danger_signs", "mahalla_activist"],
                 note="Xavf tushuntirildi, oila hozircha rad etdi").json()
    assert r["status"] == "unreachable" and r["refused_at"] and "rad" in r["unreachable_reason"]
    assert r["contact_attempts"][-1]["counselling_uz"]
    with SessionLocal() as db:
        a = db.get(Alert, aid)
        assert abs((a.retry_due_at - a.refused_at) - timedelta(hours=24)) < timedelta(minutes=1)  # RED: 24 h
        a.retry_due_at = utcnow() - timedelta(minutes=1)
        db.commit()
        run_escalations(db)
        db.refresh(a)
        assert a.events[-1].event == "retry_due" and a.retry_due_at > utcnow() + timedelta(hours=23)
        assert a.status == "unreachable"
    # a measurement arrives: contact established, the alert now waits for the closure
    _visit(client, preg, CALM, login(client, NUK, "nurse"))
    a = next(x for x in client.get("/api/alerts?status=unresolved", headers=doc).json() if x["id"] == aid)
    assert a["status"] == "acknowledged" and a["has_measurement"] and a["retry_due_at"] is None


def test_admin_sees_unreachable_counts_only(client):
    _, _, alert = _new_red_alert(client)
    _attempt(client, alert["id"], login(client, NUK, "doctor"), channel="home_visit", result="refused",
             counselling=["danger_signs"], note="Oila rad etdi, xavf tushuntirildi")
    r = client.get("/api/geo/unreachable", headers=login(client, None, "region.admin"))
    assert r.status_code == 200
    body = r.json()
    nuk = next(p for p in body["polyclinics"] if p["code"] == NUK)
    assert nuk["unreachable_red"] >= 1 and body["total"] >= nuk["unreachable_red"]
    assert set(nuk) == {"id", "code", "name", "district", "unreachable_red"}
    assert "QQR-" not in r.text and "patient" not in r.text
    assert client.get("/api/geo/unreachable", headers=login(client, NUK, "doctor")).status_code == 403
    tiles = client.get("/api/quality/tiles", headers=login(client, NUK, "department_head")).json()
    assert tiles["unreachable_red"] >= 1 and 0 <= tiles["acknowledged_without_measurement_rate"] <= 1


def test_moved_patient_transfer_follows_mahalla_and_audits_both(client):
    pid, _, alert = _new_red_alert(client)
    nurse = login(client, NUK, "nurse")
    targets = client.get("/api/transfer/mahallas", headers=nurse).json()
    sam = next(m for m in targets if m["polyclinic_code"] == SAM)
    assert set(targets[0]) == {"id", "name", "polyclinic_code", "polyclinic_name", "own"}
    r = client.post(f"/api/patients/{pid}/transfer", json={"mahalla_id": sam["id"]}, headers=nurse)
    assert r.status_code == 200 and r.json()["alerts_moved"] >= 1
    assert client.get(f"/api/patients/{pid}", headers=login(client, NUK, "doctor")).status_code == 404
    assert client.get(f"/api/patients/{pid}", headers=login(client, SAM, "doctor")).status_code == 200
    sam_alert = next(a for a in client.get("/api/alerts?status=active", headers=login(client, SAM, "specialist")).json()
                     if a["id"] == alert["id"])
    assert sam_alert["assigned_user_id"] == _uid(SAM, "specialist")
    with SessionLocal() as db:
        rows = db.scalars(select(AuditLog).where(AuditLog.entity == "patient", AuditLog.entity_id == pid,
                                                 AuditLog.action.in_(("transfer_out", "transfer_in")))).all()
    assert {r.action for r in rows} == {"transfer_out", "transfer_in"}
    assert all(r.from_polyclinic_id != r.to_polyclinic_id and r.to_polyclinic_id for r in rows)


# ---------------- tenant isolation ----------------
def test_other_tenant_cannot_touch_the_loop(client):
    pid, _, alert = _new_red_alert(client)
    aid = alert["id"]
    assert _attempt(client, aid, login(client, CHL, "nurse")).status_code == 404
    assert client.post(f"/api/alerts/{aid}/confirm", json={}, headers=login(client, CHL, "doctor")).status_code == 404
    assert client.post(f"/api/alerts/{aid}/resolve", json=RESOLVE, headers=login(client, CHL, "specialist")).status_code == 404
    assert client.post(f"/api/patients/{pid}/transfer", json={"mahalla_id": 1},
                       headers=login(client, CHL, "nurse")).status_code == 404
    for path in ("/api/quality", "/api/quality/tiles", "/api/transfer/mahallas"):
        assert client.get(path, headers=login(client, None, "region.admin")).status_code == 403


# ---------------- Part E ----------------
def test_plausibility_flags_for_department_head_only(client):
    doc = login(client, FRG, "doctor")
    opened = (utcnow() - timedelta(seconds=5)).isoformat()
    for _ in range(10):
        _, preg = _green_pregnancy(FRG)
        _visit(client, preg, {"systolic": 120, "diastolic": 80, "weight_kg": 60, "opened_at": opened}, doc)
    for role in ("nurse", "doctor", "specialist"):
        assert client.get("/api/quality", headers=login(client, FRG, role)).status_code == 403
    rep = client.get("/api/quality", headers=login(client, FRG, "department_head")).json()
    assert rep["label_uz"] == "signal, ayblov emas"
    row = next(u for u in rep["users"] if u["user_id"] == _uid(FRG, "doctor"))
    reasons = {s["reason"]: s for s in row["signals"]}
    assert {"identical_bp", "digit_bias", "low_variation", "fast_entry", "burst"} <= set(reasons)
    assert reasons["fast_entry"]["visits"] == 10 and all(c.startswith("FAR-FRG-") for c in reasons["fast_entry"]["patient_codes"])
    text = str(rep)
    assert "home" not in text and "pinfl" not in text.lower()
    # another polyclinic's department head never sees these users
    other = client.get("/api/quality", headers=login(client, NUK, "department_head")).json()
    assert all(u["user_id"] != _uid(FRG, "doctor") for u in other["users"])
