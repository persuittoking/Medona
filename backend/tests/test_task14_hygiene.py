"""Task 14: security hygiene (secrets, PINFL re-hash, external-entry rate limit + audit) and honest docs."""
import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.config import DEV_JWT_SECRET, Settings, get_settings
from app.db import SessionLocal, sync_pinfl_hashes
from app.models import AuditLog, Newborn, Patient, User
from app.security.crypto import decrypt, hash_pinfl
from tests.conftest import CHL, NUK, login

BACKEND = Path(__file__).resolve().parent.parent
GOOD = {"jwt_secret": "j" * 40, "pinfl_hash_secret": "p" * 40, "fernet_key": "k" * 44}


def _settings(**kw) -> Settings:
    return Settings(_env_file=None, **{**GOOD, **kw})


# ---------------- A1 / A3: secrets ----------------
@pytest.mark.parametrize("override,problem", [
    ({"jwt_secret": DEV_JWT_SECRET}, "JWT_SECRET"),
    ({"jwt_secret": ""}, "JWT_SECRET"),
    ({"pinfl_hash_secret": ""}, "PINFL_HASH_SECRET is empty"),
    ({"pinfl_hash_secret": "j" * 40}, "must differ"),
    ({"fernet_key": ""}, "FERNET_KEY"),
])
def test_production_refuses_weak_secrets(override, problem):
    s = _settings(demo_mode=False, **override)
    with pytest.raises(RuntimeError, match=problem):
        s.check_secrets()
    _settings(demo_mode=True, **override).check_secrets()  # DEMO_MODE keeps the dev fallback


def test_production_starts_with_good_secrets():
    s = _settings(demo_mode=False)
    assert s.secret_problems() == []
    s.check_secrets()


def test_make_env_generates_separate_pinfl_secret(tmp_path):
    from app.make_env import make_env

    target = tmp_path / ".env"
    assert make_env(target, BACKEND / ".env.example")
    env = dict(line.split("=", 1) for line in target.read_text(encoding="utf-8").splitlines()
               if "=" in line and not line.startswith("#"))
    assert env["JWT_SECRET"] and env["PINFL_HASH_SECRET"] and env["FERNET_KEY"]
    assert env["PINFL_HASH_SECRET"] != env["JWT_SECRET"]
    assert not make_env(target, BACKEND / ".env.example")  # never overwrites an existing .env
    example = (BACKEND / ".env.example").read_text(encoding="utf-8")
    assert "\nPINFL_HASH_SECRET=\n" in example and "\nJWT_SECRET=\n" in example  # template stays empty


def test_changed_pinfl_secret_rehashes_every_patient(client):
    s = get_settings()
    old = s.pinfl_hash_secret
    assert sync_pinfl_hashes() == 0  # fingerprint stored at startup: nothing to do
    try:
        s.pinfl_hash_secret = "rotated-" + "x" * 40
        with SessionLocal() as db:
            total = db.scalar(select(func.count()).select_from(Patient))
        assert sync_pinfl_hashes() == total  # key changed -> ALL rows recomputed
        assert sync_pinfl_hashes() == 0
        with SessionLocal() as db:
            pat = db.scalars(select(Patient).where(Patient.code == "QQR-NUK-DEMO1")).one()
            pinfl = decrypt(pat.pinfl_enc)
            assert pat.pinfl_hash == hash_pinfl(pinfl)
        r = client.post("/api/external/lookup", json={"pinfl": pinfl}, headers=login(client, CHL, "nurse"))
        assert r.status_code == 200 and r.json()["patient_code"] == "QQR-NUK-DEMO1"
    finally:
        s.pinfl_hash_secret = old
        sync_pinfl_hashes()


# ---------------- A2: external entry by any identifier: rate limit + audit ----------------
def _lookups(user_id: int) -> list[AuditLog]:
    with SessionLocal() as db:
        return list(db.scalars(select(AuditLog).where(
            AuditLog.user_id == user_id, AuditLog.action.in_(("external_lookup", "external_lookup_miss")))).all())


def _user_id(username: str, code: str) -> int:
    from app.models import Polyclinic

    with SessionLocal() as db:
        pc = db.scalars(select(Polyclinic).where(Polyclinic.code == code)).one()
        return db.scalars(select(User.id).where(User.polyclinic_id == pc.id, User.username == username)).one()


VISIT = {"systolic": 118, "diastolic": 76, "weight_kg": 60}


def test_external_entry_by_code_or_id_is_audited_hit_and_miss(client):
    h = login(client, CHL, "doctor")
    uid = _user_id("doctor", CHL)
    before = len(_lookups(uid))
    with SessionLocal() as db:
        pat = db.scalars(select(Patient).where(Patient.code == "QQR-NUK-DEMO3")).one()
        preg_id = pat.pregnancies[0].id
        nb = db.scalars(select(Newborn).where(Newborn.code == "B-QQR-NUK-DEMO5-1")).one()
    cases = [
        ("/api/external/visits", {"patient_code": "QQR-NUK-NOPE", **VISIT}, 404, "patient_code"),
        ("/api/external/visits", {"pregnancy_id": 999999, **VISIT}, 404, "pregnancy_id"),
        ("/api/external/visits", {"patient_code": "QQR-NUK-DEMO3", **VISIT}, 201, "patient_code"),
        ("/api/external/visits", {"pregnancy_id": preg_id, **VISIT}, 201, "pregnancy_id"),
        ("/api/external/checks", {"child_code": "B-NOPE-1", "weight_g": 7000}, 404, "child_code"),
        ("/api/external/checks", {"newborn_id": nb.id, "weight_g": 7000, "temperature_c": 36.7}, 201, "newborn_id"),
    ]
    for path, body, status, by in cases:
        r = client.post(path, json=body, headers=h)
        assert r.status_code == status, (path, body, r.text[:200])
        last = _lookups(uid)[-1]
        assert last.action == ("external_lookup_miss" if status == 404 else "external_lookup")
        assert f"by={by}" in (last.details or "") and last.from_polyclinic_id is not None
        if status == 201:
            assert last.to_polyclinic_id is not None and last.entity_id is not None
    assert len(_lookups(uid)) == before + len(cases)


def test_external_entry_shares_the_hourly_limit(client):
    h = login(client, CHL, "nurse")
    uid = _user_id("nurse", CHL)
    with SessionLocal() as db:
        n = len(_lookups(uid))
        db.add_all([AuditLog(user_id=uid, action="external_lookup_miss", entity="patient") for _ in range(30 - n)])
        db.commit()
    for path, body in [("/api/external/visits", {"patient_code": "QQR-NUK-DEMO3", **VISIT}),
                       ("/api/external/visits", {"pregnancy_id": 1, **VISIT}),
                       ("/api/external/checks", {"child_code": "B-QQR-NUK-DEMO5-1", "weight_g": 7000}),
                       ("/api/external/lookup", {"pinfl": "12345678901234"})]:
        assert client.post(path, json=body, headers=h).status_code == 429, path
    assert len(_lookups(uid)) == 30  # rejected calls do not add rows
    # other users keep their own limit
    assert client.post("/api/external/visits", json={"patient_code": "QQR-NUK-DEMO3", **VISIT},
                       headers=login(client, NUK, "doctor")).status_code == 201


# ---------------- B: honest labels ----------------
def test_model_docs_quote_metrics_json():
    from ml.metrics_docs import DOCS, extract_block, render_block

    metrics = json.loads((BACKEND / "ml" / "artifacts" / "metrics.json").read_text(encoding="utf-8"))
    expected = render_block(metrics)
    for doc in DOCS:
        assert extract_block(doc.read_text(encoding="utf-8")) == expected, f"{doc.name}: run python -m ml.metrics_docs"
    assert f"{metrics['test']['roc_auc']:.3f}" in expected


def test_visit_calendar_is_labelled_demo():
    src = (BACKEND / "app" / "risk" / "thresholds.py").read_text(encoding="utf-8")
    assert "DEMO calendar, to be replaced by the national schedule confirmed by an obstetrician" in src


# ---------------- D: demo readiness ----------------
def test_llm_health_reports_demo_summary_counts_only(client):
    for code in ("QQR-NUK-DEMO1", "QQR-NUK-DEMO2"):  # without a key the template is built on first view
        with SessionLocal() as db:
            preg = db.scalars(select(Patient).where(Patient.code == code)).one().pregnancies[0].id
        client.get(f"/api/llm/summary/{preg}", headers=login(client, NUK, "doctor"))
    r = client.get("/api/llm/health", headers=login(client, None, "region.admin"))
    d = r.json()["demo_summaries"]
    assert set(d) == {"total", "cached", "ai", "template"} and d["total"] == 6 and d["cached"] >= 2
    assert "DEMO" not in r.text and "QQR-" not in r.text
    assert client.get("/api/llm/health", headers=login(client, NUK, "doctor")).status_code == 403
