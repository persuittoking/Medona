"""Maps.

- /api/polyclinic/map      staff only: own mahalla polygons + patient home points (personal data, audited)
- /api/public/territories  no auth: demo polyclinic territory outlines (no counts, no patients) for the login map
- /api/geo/...             admins only: AGGREGATED COUNTS ONLY (no names, codes or home points)
"""
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import audit, require_admin
from app.api.tenancy import Tenant, staff
from app.db import get_db
from app.models import Alert, District, Mahalla, Patient, Polyclinic, Pregnancy, Region, User
from app.services.geo import decrypt_home

router = APIRouter(prefix="/api", tags=["geo"])

AGG_KEYS = ("red", "yellow", "green", "total", "red_share", "open_alerts")


def _mahalla_out(m: Mahalla) -> dict:
    return {"id": m.id, "name": m.name, "boundary": m.boundary_geojson, "centroid": [m.centroid_lat, m.centroid_lon],
            "demo_boundary": m.demo_boundary, "source": m.boundary_source}


@router.get("/polyclinic/map")
def polyclinic_map(request: Request, t: Tenant = Depends(staff())) -> dict:
    pc = t.db.get(Polyclinic, t.polyclinic_id)
    stmt = select(Patient, Pregnancy).join(Pregnancy, Pregnancy.patient_id == Patient.id).where(Pregnancy.status == "active")
    points = []
    for pat, preg in t.db.execute(t.patients(stmt)).all():
        lat, lon = decrypt_home(pat.home_enc)
        points.append({"patient_id": pat.id, "pregnancy_id": preg.id, "code": pat.code, "zone": preg.current_zone,
                       "risk": preg.current_risk_score, "lat": lat, "lon": lon, "mahalla_id": pat.mahalla_id})
    audit(t.db, t.user, "view_home_points", "polyclinic", pc.id, request)
    t.db.commit()
    return {"polyclinic": {"id": pc.id, "code": pc.code, "name": pc.name, "lat": pc.lat, "lon": pc.lon},
            "mahallas": [_mahalla_out(m) for m in pc.mahallas], "points": points}


@router.get("/public/territories")
def public_territories(db: Session = Depends(get_db)) -> list[dict]:
    out = []
    for pc in db.scalars(select(Polyclinic).order_by(Polyclinic.id)).all():
        out.append({"code": pc.code, "name": pc.name, "district": pc.district.name,
                    "mahallas": [{"name": m.name, "boundary": m.boundary_geojson} for m in pc.mahallas]})
    return out


# ---------------- admin aggregates ----------------
def _counts_by_polyclinic(db: Session) -> dict[int, dict]:
    agg: dict[int, dict] = defaultdict(lambda: {"red": 0, "yellow": 0, "green": 0, "total": 0, "open_alerts": 0})
    rows = db.execute(select(Patient.polyclinic_id, Pregnancy.current_zone, func.count())
                      .join(Pregnancy, Pregnancy.patient_id == Patient.id).where(Pregnancy.status == "active")
                      .group_by(Patient.polyclinic_id, Pregnancy.current_zone)).all()
    for pc_id, zone, n in rows:
        agg[pc_id][zone] += n
        agg[pc_id]["total"] += n
    alerts = db.execute(select(Patient.polyclinic_id, func.count()).select_from(Alert)
                        .join(Pregnancy, Alert.pregnancy_id == Pregnancy.id).join(Patient, Pregnancy.patient_id == Patient.id)
                        .where(Alert.status.in_(("open", "escalated"))).group_by(Patient.polyclinic_id)).all()
    for pc_id, n in alerts:
        agg[pc_id]["open_alerts"] += n
    return agg


def _sum(parts: list[dict]) -> dict:
    s = {k: sum(p[k] for p in parts) for k in ("red", "yellow", "green", "total", "open_alerts")}
    s["red_share"] = round(s["red"] / s["total"], 3) if s["total"] else 0.0
    return s


def _can_see_region(user: User, region_id: int) -> bool:
    return user.region_id == region_id


def _can_see_district(user: User, district: District) -> bool:
    if user.role == "district_admin":
        return user.district_id == district.id
    return user.region_id == district.region_id


def _district_parts(db: Session, d: District, agg: dict[int, dict]) -> list[dict]:
    return [agg.get(pc.id, _sum([])) for pc in db.scalars(select(Polyclinic).where(Polyclinic.district_id == d.id)).all()]


@router.get("/geo/country")
def geo_country(user: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    agg = _counts_by_polyclinic(db)
    regions = []
    for r in db.scalars(select(Region).order_by(Region.id)).all():
        node = {"id": r.id, "name": r.name, "lat": r.lat, "lon": r.lon, "accessible": _can_see_region(user, r.id)}
        if node["accessible"]:
            districts = [d for d in r.districts if _can_see_district(user, d)]
            node.update(_sum([x for d in districts for x in _district_parts(db, d, agg)]))
        regions.append(node)
    return {"level": "country", "name": "O'zbekiston", "children": regions}


@router.get("/geo/regions/{region_id}")
def geo_region(region_id: int, user: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    r = db.get(Region, region_id)
    if r is None or not _can_see_region(user, r.id):
        raise HTTPException(404, "Topilmadi")
    agg = _counts_by_polyclinic(db)
    children = []
    for d in r.districts:
        node = {"id": d.id, "name": d.name, "lat": d.lat, "lon": d.lon, "accessible": _can_see_district(user, d)}
        if node["accessible"]:
            node.update(_sum(_district_parts(db, d, agg)))
            node["polyclinics"] = len(_district_parts(db, d, agg))
        children.append(node)
    return {"level": "region", "id": r.id, "name": r.name, "children": children,
            "breadcrumb": [{"level": "country", "name": "O'zbekiston"}]}


@router.get("/geo/districts/{district_id}")
def geo_district(district_id: int, user: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    d = db.get(District, district_id)
    if d is None or not _can_see_district(user, d):
        raise HTTPException(404, "Topilmadi")
    agg = _counts_by_polyclinic(db)
    children = []
    for pc in db.scalars(select(Polyclinic).where(Polyclinic.district_id == d.id)).all():
        children.append({"id": pc.id, "code": pc.code, "name": pc.name, "lat": pc.lat, "lon": pc.lon, "accessible": True,
                         "territory": [{"name": m.name, "boundary": m.boundary_geojson} for m in pc.mahallas],
                         **_sum([agg.get(pc.id, _sum([]))])})
    return {"level": "district", "id": d.id, "name": d.name, "children": children,
            "breadcrumb": [{"level": "country", "name": "O'zbekiston"}, {"level": "region", "id": d.region_id, "name": d.region.name}]}


@router.get("/geo/polyclinics/{polyclinic_id}")
def geo_polyclinic(polyclinic_id: int, user: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    pc = db.get(Polyclinic, polyclinic_id)
    if pc is None or not _can_see_district(user, pc.district):
        raise HTTPException(404, "Topilmadi")
    agg = _counts_by_polyclinic(db)
    return {"level": "polyclinic", "id": pc.id, "code": pc.code, "name": pc.name, "lat": pc.lat, "lon": pc.lon,
            "territory": [{"name": m.name, "boundary": m.boundary_geojson} for m in pc.mahallas],
            **_sum([agg.get(pc.id, _sum([]))]),
            "breadcrumb": [{"level": "country", "name": "O'zbekiston"},
                           {"level": "region", "id": pc.district.region_id, "name": pc.district.region.name},
                           {"level": "district", "id": pc.district_id, "name": pc.district.name}]}
