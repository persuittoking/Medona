"""TENANT ISOLATION: a user of polyclinic A must never read or change polyclinic B's data, through ANY endpoint."""
import pytest

from app.db import SessionLocal
from app.models import Alert, Patient, Pregnancy
from tests.conftest import CHL, FRG, NUK, demo, login

VISIT = {"systolic": 120, "diastolic": 80}


def _other_tenant_ids():
    """Ids belonging to PL-NUK-001: a patient, its pregnancy and an alert."""
    pid, preg = demo("QQR-NUK-DEMO1")
    with SessionLocal() as db:
        alert = db.query(Alert).join(Pregnancy, Alert.pregnancy_id == Pregnancy.id) \
            .join(Patient, Pregnancy.patient_id == Patient.id).filter(Patient.code.like("QQR-NUK-%")).first()
        assert alert is not None, "seed should create at least one alert in PL-NUK-001"
        return {"pid": pid, "preg": preg, "alert": alert.id}


# (method, path template, json body) — every patient-level endpoint
ENDPOINTS = [
    ("GET", "/api/patients/{pid}", None),
    ("POST", "/api/patients/{pid}/reveal", None),
    ("POST", "/api/risk/preview", {"pregnancy_id": "{preg}", **VISIT}),
    ("POST", "/api/visits", {"pregnancy_id": "{preg}", **VISIT}),
    ("POST", "/api/alerts/{alert}/ack", {"action_taken": "boshqa poliklinika"}),
    ("POST", "/api/alerts/{alert}/resolve", {"action_taken": "boshqa poliklinika"}),
    ("GET", "/api/llm/summary/{preg}", None),
]
# Role limits that apply BEFORE any lookup (a 403 there reveals nothing about the other tenant).
ROLE_ONLY = {"/api/visits": {"nurse", "doctor"}, "/api/alerts/{alert}/ack": {"specialist", "doctor"},
             "/api/alerts/{alert}/resolve": {"specialist", "doctor"}}


def _call(client, method, path, body, ids, headers):
    path = path.format(**ids)
    if body is not None:
        body = {k: (ids["preg"] if v == "{preg}" else v) for k, v in body.items()}
    return client.request(method, path, json=body, headers=headers)


@pytest.mark.parametrize("method,path,body", ENDPOINTS)
@pytest.mark.parametrize("polyclinic,role", [(CHL, "nurse"), (CHL, "doctor"), (FRG, "specialist")])
def test_other_polyclinic_gets_404(client, method, path, body, polyclinic, role):
    ids = _other_tenant_ids()
    r = _call(client, method, path, body, ids, login(client, polyclinic, role))
    expected = 403 if role not in ROLE_ONLY.get(path, {role}) else 404
    assert r.status_code == expected, f"{role}@{polyclinic} {method} {path} -> {r.status_code} {r.text[:120]}"


@pytest.mark.parametrize("method,path,body", ENDPOINTS + [("GET", "/api/patients", None), ("GET", "/api/alerts", None),
                                                          ("GET", "/api/polyclinic/map", None),
                                                          ("GET", "/api/dashboard/summary", None),
                                                          ("GET", "/api/dashboard/top", None)])
@pytest.mark.parametrize("admin", ["district.admin", "region.admin"])
def test_admins_get_403_on_patient_level_endpoints(client, method, path, body, admin):
    ids = _other_tenant_ids()
    r = _call(client, method, path, body, ids, login(client, None, admin))
    assert r.status_code == 403


def test_owner_still_has_access(client):
    ids = _other_tenant_ids()
    h = login(client, NUK, "specialist")
    assert client.get(f"/api/patients/{ids['pid']}", headers=h).status_code == 200
    assert client.get(f"/api/llm/summary/{ids['preg']}", headers=h).status_code == 200


def test_lists_never_contain_other_tenants(client):
    for code, prefix in [(NUK, "QQR-NUK-"), (CHL, "TSH-CHL-"), (FRG, "FAR-FRG-")]:
        h = login(client, code, "doctor")
        assert all(r["code"].startswith(prefix) for r in client.get("/api/patients", headers=h).json())
        assert all(a["patient_code"].startswith(prefix) for a in client.get("/api/alerts", headers=h).json())
        assert all(r["code"].startswith(prefix) for r in client.get("/api/dashboard/top", headers=h).json())
        m = client.get("/api/polyclinic/map", headers=h).json()
        assert m["polyclinic"]["code"] == code and all(p["code"].startswith(prefix) for p in m["points"])


def test_unknown_id_and_other_tenant_look_the_same(client):
    """No existence leak: another tenant's patient is indistinguishable from a non-existent one."""
    ids = _other_tenant_ids()
    h = login(client, CHL, "nurse")
    a = client.get(f"/api/patients/{ids['pid']}", headers=h)
    b = client.get("/api/patients/999999", headers=h)
    assert a.status_code == b.status_code == 404 and a.json() == b.json()


def test_dependency_is_used_by_every_patient_router():
    """Guard: patient-level routers must not bypass app/api/tenancy.py."""
    from pathlib import Path

    api = Path(__file__).resolve().parent.parent / "app" / "api"
    for name in ("patients.py", "visits.py", "alerts.py", "llm.py"):
        src = (api / name).read_text(encoding="utf-8")
        assert "staff(" in src and "current_user" not in src, name
