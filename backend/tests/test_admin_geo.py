"""Admin drill-down: aggregated counts only, correct sums, scope limits."""
import json

from app.db import SessionLocal
from app.models import District, Patient, Polyclinic, Pregnancy, Region
from tests.conftest import NUK, login

ALLOWED_NODE_KEYS = {"id", "name", "code", "lat", "lon", "accessible", "territory", "polyclinics",
                     "red", "yellow", "green", "total", "red_share", "open_alerts"}
FORBIDDEN = ("QQR-NUK-", "TSH-CHL-", "FAR-FRG-", "patient", "home", "pinfl", "full_name", "phone", "points")


def _ids():
    with SessionLocal() as db:
        pc = db.query(Polyclinic).filter_by(code=NUK).one()
        return {"region": pc.district.region_id, "district": pc.district_id, "polyclinic": pc.id,
                "tsh_region": db.query(Region).filter_by(code="TSH").one().id,
                "chl_district": db.query(District).filter_by(code="CHL").one().id,
                "xoj_district": db.query(District).filter_by(code="XOJ").one().id}


def _no_individual_data(payload):
    text = json.dumps(payload, ensure_ascii=False)
    for word in FORBIDDEN:
        assert word not in text, word
    for node in payload.get("children", []):
        assert set(node) <= ALLOWED_NODE_KEYS, set(node) - ALLOWED_NODE_KEYS


def test_drilldown_aggregates_only(client):
    ids = _ids()
    h = login(client, None, "region.admin")
    country = client.get("/api/geo/country", headers=h).json()
    region = client.get(f"/api/geo/regions/{ids['region']}", headers=h).json()
    district = client.get(f"/api/geo/districts/{ids['district']}", headers=h).json()
    pc = client.get(f"/api/geo/polyclinics/{ids['polyclinic']}", headers=h).json()
    for payload in (country, region, district):
        _no_individual_data(payload)
    _no_individual_data({k: v for k, v in pc.items() if k != "code"})
    assert [b["name"] for b in pc["breadcrumb"]] == ["O'zbekiston", "Qoraqalpog'iston Respublikasi", "Nukus shahri"]


def test_counts_add_up(client):
    ids = _ids()
    h = login(client, None, "region.admin")
    with SessionLocal() as db:
        truth = db.query(Pregnancy).join(Patient).filter(Pregnancy.status == "active",
                                                          Patient.polyclinic_id == ids["polyclinic"]).count()
    pc = client.get(f"/api/geo/polyclinics/{ids['polyclinic']}", headers=h).json()
    assert pc["total"] == truth == pc["red"] + pc["yellow"] + pc["green"]
    qqr = next(r for r in client.get("/api/geo/country", headers=h).json()["children"] if r["id"] == ids["region"])
    region = client.get(f"/api/geo/regions/{ids['region']}", headers=h).json()
    assert qqr["total"] == sum(d.get("total", 0) for d in region["children"]) == truth  # only one polyclinic in QQR
    assert 0 <= qqr["red_share"] <= 1


def test_region_admin_scope(client):
    ids = _ids()
    h = login(client, None, "region.admin")
    country = client.get("/api/geo/country", headers=h).json()["children"]
    other = next(r for r in country if r["id"] == ids["tsh_region"])
    assert other["accessible"] is False and "total" not in other
    assert client.get(f"/api/geo/regions/{ids['tsh_region']}", headers=h).status_code == 404
    assert client.get(f"/api/geo/districts/{ids['chl_district']}", headers=h).status_code == 404


def test_district_admin_scope(client):
    ids = _ids()
    h = login(client, None, "district.admin")
    assert client.get(f"/api/geo/districts/{ids['district']}", headers=h).status_code == 200
    assert client.get(f"/api/geo/districts/{ids['xoj_district']}", headers=h).status_code == 404
    region = client.get(f"/api/geo/regions/{ids['region']}", headers=h).json()
    visible = [d for d in region["children"] if d["accessible"]]
    assert [d["id"] for d in visible] == [ids["district"]]


def test_staff_cannot_use_admin_endpoints(client):
    assert client.get("/api/geo/country", headers=login(client, NUK, "doctor")).status_code == 403
