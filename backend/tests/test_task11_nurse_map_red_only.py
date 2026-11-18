"""Task 11: the nurse map shows red-zone home points only; nurses get no polyclinic search."""
import pytest
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import AuditLog
from tests.conftest import CHL, NUK, SAM, login

SUBJECTS = ("pregnancy", "child", "all")


@pytest.mark.parametrize("subject", SUBJECTS)
def test_nurse_map_has_only_red_points(client, subject):
    m = client.get(f"/api/polyclinic/map?subject={subject}", headers=login(client, NUK, "nurse")).json()
    assert m["red_only"] is True
    assert m["points"] and all(p["zone"] == "red" for p in m["points"])
    kinds = {p["kind"] for p in m["points"]}
    assert "pregnancy" in kinds


def test_nurse_map_red_children_present_if_any(client):
    doc = client.get("/api/polyclinic/map?subject=child", headers=login(client, NUK, "doctor")).json()
    nurse = client.get("/api/polyclinic/map?subject=child", headers=login(client, NUK, "nurse")).json()
    red_kids = {p["newborn_id"] for p in doc["points"] if p["kind"] == "child" and p["zone"] == "red"}
    assert {p["newborn_id"] for p in nurse["points"] if p["kind"] == "child"} == red_kids


def test_doctor_map_keeps_all_zones(client):
    m = client.get("/api/polyclinic/map?subject=all", headers=login(client, NUK, "doctor")).json()
    assert m["red_only"] is False
    assert {"red", "yellow", "green"} <= {p["zone"] for p in m["points"]}


@pytest.mark.parametrize("subject", SUBJECTS)
def test_nurse_mahalla_aggregates_unchanged(client, subject):
    for code in (NUK, SAM):
        doc = client.get(f"/api/polyclinic/map?subject={subject}", headers=login(client, code, "doctor")).json()
        nurse = client.get(f"/api/polyclinic/map?subject={subject}", headers=login(client, code, "nurse")).json()
        assert nurse["mahallas"] == doc["mahallas"]
        assert nurse["subject_counts"] == doc["subject_counts"]
        for x in nurse["mahallas"]:
            assert x["total"] == x["red"] + x["yellow"] + x["green"]
            assert x["red"] == sum(1 for p in nurse["points"] if p["mahalla_id"] == x["id"]
                                   and (subject == "all" or p["kind"] == subject))


def test_nurse_red_points_tenant_isolated(client):
    for code, prefix in [(NUK, "QQR-NUK-"), (CHL, "TSH-CHL-"), (SAM, "SAM-")]:
        m = client.get("/api/polyclinic/map?subject=all", headers=login(client, code, "nurse")).json()
        assert m["polyclinic"]["code"] == code
        own = {x["id"] for x in m["mahallas"]}
        assert all(p["zone"] == "red" and p["mahalla_id"] in own for p in m["points"])
        if prefix != "SAM-":
            assert all(p["code"].removeprefix("B-").startswith(prefix) for p in m["points"])


def test_nurse_map_still_audited(client):
    h = login(client, NUK, "nurse")
    with SessionLocal() as db:
        before = db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "view_home_points"))
    client.get("/api/polyclinic/map", headers=h)
    with SessionLocal() as db:
        after = db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "view_home_points"))
    assert after == before + 1


def test_polyclinic_search_forbidden_for_nurse(client):
    for code in (NUK, SAM):
        assert client.get("/api/geo/polyclinics/search?q=Nukus", headers=login(client, code, "nurse")).status_code == 403
        assert client.get("/api/geo/polyclinics/search?q=Nukus", headers=login(client, code, "doctor")).status_code == 200
    assert client.get("/api/geo/polyclinics/search", headers=login(client, None, "region.admin")).status_code == 200
