"""Maps.

- /api/polyclinic/map      staff only: own mahalla polygons + home points of pregnant women and children 0-12 months
                           (a child is shown at the mother's home point; personal data, audited)
- /api/public/territories  no auth: demo polyclinic territory outlines (no counts, no patients) for the login map
- /api/geo/...             admins only: AGGREGATED COUNTS ONLY (no names, codes or home points);
                           ?subject=pregnancy|child|all (default pregnancy), `subject_counts` for the switch
"""
import re
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import audit, current_user, require_admin
from app.api.tenancy import Tenant, staff
from app.db import get_db
from app.models import (
    Alert,
    District,
    Mahalla,
    Newborn,
    Patient,
    Polyclinic,
    Pregnancy,
    Region,
    User,
)
from app.services.geo import decrypt_home

router = APIRouter(prefix="/api", tags=["geo"])

AGG_KEYS = ("red", "yellow", "green", "total", "red_share", "open_alerts")
SubjectQ = Query("pregnancy", pattern="^(pregnancy|child|all)$")
_APOS_RE = re.compile(r"['‘’ʻʼ`´ʹ]")


def normalize_uz(text: str) -> str:
    """Normalize Uzbek Latin apostrophe variants (o‘/o'/oʻ, g‘/g'/gʻ) to a single ASCII apostrophe."""
    return _APOS_RE.sub("'", (text or "").lower()).strip()


def matches_uz(query: str, *fields: str) -> bool:
    q = normalize_uz(query)
    if not q:
        return True
    q_bare = q.replace("'", "")
    for f in fields:
        norm = normalize_uz(f)
        if q in norm or (q_bare and q_bare in norm.replace("'", "")):
            return True
    return False


def _mahalla_out(m: Mahalla, agg: dict | None = None) -> dict:
    out = {"id": m.id, "name": m.name, "boundary": m.boundary_geojson, "centroid": [m.centroid_lat, m.centroid_lon],
           "demo_boundary": m.demo_boundary, "source": m.boundary_source}
    if agg is not None:
        out.update(_sum([agg]))
    return out


@router.get("/polyclinic/map")
def polyclinic_map(request: Request, subject: str = SubjectQ, t: Tenant = Depends(staff())) -> dict:
    pc = t.db.get(Polyclinic, t.polyclinic_id)
    stmt = select(Patient, Pregnancy).join(Pregnancy, Pregnancy.patient_id == Patient.id).where(Pregnancy.status == "active")
    points = []
    for pat, preg in t.db.execute(t.patients(stmt)).all():
        lat, lon = decrypt_home(pat.home_enc)
        points.append({"kind": "pregnancy", "patient_id": pat.id, "pregnancy_id": preg.id, "newborn_id": None,
                       "code": pat.code, "zone": preg.current_zone, "risk": preg.current_risk_score,
                       "lat": lat, "lon": lon, "mahalla_id": pat.mahalla_id})
    for nb in t.db.scalars(t.children(select(Newborn).where(Newborn.status == "active"))).all():
        pat = nb.pregnancy.patient
        lat, lon = decrypt_home(pat.home_enc)
        points.append({"kind": "child", "patient_id": pat.id, "pregnancy_id": None, "newborn_id": nb.id,
                       "code": nb.code, "zone": nb.current_zone, "risk": None,
                       "lat": lat, "lon": lon, "mahalla_id": nb.mahalla_id})
    m_agg = _counts_by_mahalla(t.db, subject)
    audit(t.db, t.user, "view_home_points", "polyclinic", pc.id, request)
    t.db.commit()
    return {"polyclinic": {"id": pc.id, "code": pc.code, "name": pc.name, "lat": pc.lat, "lon": pc.lon},
            "mahallas": [_mahalla_out(m, m_agg.get(m.id, _sum([]))) for m in pc.mahallas], "points": points}


@router.get("/public/territories")
def public_territories(db: Session = Depends(get_db)) -> list[dict]:
    out = []
    for pc in db.scalars(select(Polyclinic).order_by(Polyclinic.id)).all():
        out.append({"code": pc.code, "name": pc.name, "district": pc.district.name,
                    "mahallas": [{"name": m.name, "boundary": m.boundary_geojson} for m in pc.mahallas]})
    return out


# ---------------- admin aggregates ----------------


def _counts_by_polyclinic(db: Session, subject: str = "pregnancy") -> dict[int, dict]:
    """Zone counts + open alerts per polyclinic for pregnancies, children 0-12 months, or both. Counts only."""
    agg: dict[int, dict] = defaultdict(lambda: {"red": 0, "yellow": 0, "green": 0, "total": 0, "open_alerts": 0})
    rows: list = []
    active = Alert.status.in_(("open", "escalated"))
    if subject != "child":
        rows += db.execute(select(Patient.polyclinic_id, Pregnancy.current_zone, func.count())
                           .join(Pregnancy, Pregnancy.patient_id == Patient.id).where(Pregnancy.status == "active")
                           .group_by(Patient.polyclinic_id, Pregnancy.current_zone)).all()
        rows += [(pc, "_alert", n) for pc, n in db.execute(
            select(Patient.polyclinic_id, func.count()).select_from(Alert)
            .join(Pregnancy, Alert.pregnancy_id == Pregnancy.id).join(Patient, Pregnancy.patient_id == Patient.id)
            .where(active).group_by(Patient.polyclinic_id)).all()]
    if subject != "pregnancy":
        rows += db.execute(select(Newborn.polyclinic_id, Newborn.current_zone, func.count())
                           .where(Newborn.status == "active").group_by(Newborn.polyclinic_id, Newborn.current_zone)).all()
        rows += [(pc, "_alert", n) for pc, n in db.execute(
            select(Newborn.polyclinic_id, func.count()).select_from(Alert).join(Newborn, Alert.newborn_id == Newborn.id)
            .where(active).group_by(Newborn.polyclinic_id)).all()]
    for pc_id, zone, n in rows:
        if zone == "_alert":
            agg[pc_id]["open_alerts"] += n
        else:
            agg[pc_id][zone] += n
            agg[pc_id]["total"] += n
    return agg


def _counts_by_mahalla(db: Session, subject: str = "pregnancy") -> dict[int, dict]:
    """Zone counts + open alerts per mahalla for pregnancies, children 0-12 months, or both. Counts only."""
    agg: dict[int, dict] = defaultdict(lambda: {"red": 0, "yellow": 0, "green": 0, "total": 0, "open_alerts": 0})
    rows: list = []
    active = Alert.status.in_(("open", "escalated"))
    if subject != "child":
        rows += db.execute(select(Patient.mahalla_id, Pregnancy.current_zone, func.count())
                           .join(Pregnancy, Pregnancy.patient_id == Patient.id).where(Pregnancy.status == "active")
                           .group_by(Patient.mahalla_id, Pregnancy.current_zone)).all()
        rows += [(m_id, "_alert", n) for m_id, n in db.execute(
            select(Patient.mahalla_id, func.count()).select_from(Alert)
            .join(Pregnancy, Alert.pregnancy_id == Pregnancy.id).join(Patient, Pregnancy.patient_id == Patient.id)
            .where(active).group_by(Patient.mahalla_id)).all()]
    if subject != "pregnancy":
        rows += db.execute(select(Newborn.mahalla_id, Newborn.current_zone, func.count())
                           .where(Newborn.status == "active").group_by(Newborn.mahalla_id, Newborn.current_zone)).all()
        rows += [(m_id, "_alert", n) for m_id, n in db.execute(
            select(Newborn.mahalla_id, func.count()).select_from(Alert).join(Newborn, Alert.newborn_id == Newborn.id)
            .where(active).group_by(Newborn.mahalla_id)).all()]
    for m_id, zone, n in rows:
        if m_id is None:
            continue
        if zone == "_alert":
            agg[m_id]["open_alerts"] += n
        else:
            agg[m_id][zone] += n
            agg[m_id]["total"] += n
    return agg


def _subject_counts(db: Session, polyclinic_ids: list[int]) -> dict[str, int]:
    """Totals per subject inside the admin's current (visible) scope, for the switch segments."""
    preg, kids = _counts_by_polyclinic(db, "pregnancy"), _counts_by_polyclinic(db, "child")
    p = sum(preg[i]["total"] for i in polyclinic_ids if i in preg)
    c = sum(kids[i]["total"] for i in polyclinic_ids if i in kids)
    return {"pregnancy": p, "child": c, "all": p + c}


def _visible_polyclinics(db: Session, user: User, districts: list[District] | None = None) -> list[int]:
    ds = districts if districts is not None else list(db.scalars(select(District)).all())
    ok = [d.id for d in ds if _can_see_district(user, d)]
    return list(db.scalars(select(Polyclinic.id).where(Polyclinic.district_id.in_(ok))).all()) if ok else []


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
def geo_country(subject: str = SubjectQ, user: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    agg = _counts_by_polyclinic(db, subject)
    regions = []
    for r in db.scalars(select(Region).order_by(Region.id)).all():
        node = {"id": r.id, "name": r.name, "lat": r.lat, "lon": r.lon, "accessible": _can_see_region(user, r.id)}
        if node["accessible"]:
            districts = [d for d in r.districts if _can_see_district(user, d)]
            node.update(_sum([x for d in districts for x in _district_parts(db, d, agg)]))
        regions.append(node)
    return {"level": "country", "name": "O'zbekiston", "children": regions, "subject": subject,
            "subject_counts": _subject_counts(db, _visible_polyclinics(db, user))}


@router.get("/geo/regions/{region_id}")
def geo_region(region_id: int, subject: str = SubjectQ, user: User = Depends(require_admin),
               db: Session = Depends(get_db)) -> dict:
    r = db.get(Region, region_id)
    if r is None or not _can_see_region(user, r.id):
        raise HTTPException(404, "Topilmadi")
    agg = _counts_by_polyclinic(db, subject)
    children = []
    for d in r.districts:
        node = {"id": d.id, "name": d.name, "lat": d.lat, "lon": d.lon, "accessible": _can_see_district(user, d)}
        if node["accessible"]:
            node.update(_sum(_district_parts(db, d, agg)))
            node["polyclinics"] = len(_district_parts(db, d, agg))
        children.append(node)
    return {"level": "region", "id": r.id, "name": r.name, "children": children, "subject": subject,
            "subject_counts": _subject_counts(db, _visible_polyclinics(db, user, list(r.districts))),
            "breadcrumb": [{"level": "country", "name": "O'zbekiston"}]}


@router.get("/geo/districts/{district_id}")
def geo_district(district_id: int, subject: str = SubjectQ, user: User = Depends(require_admin),
                 db: Session = Depends(get_db)) -> dict:
    d = db.get(District, district_id)
    if d is None or not _can_see_district(user, d):
        raise HTTPException(404, "Topilmadi")
    agg = _counts_by_polyclinic(db, subject)
    m_agg = _counts_by_mahalla(db, subject)
    children = []
    for pc in db.scalars(select(Polyclinic).where(Polyclinic.district_id == d.id)).all():
        children.append({
            "id": pc.id, "code": pc.code, "name": pc.name, "lat": pc.lat, "lon": pc.lon, "accessible": True,
            "territory": [{"id": m.id, "name": m.name, "boundary": m.boundary_geojson,
                           **_sum([m_agg.get(m.id, _sum([]))])} for m in pc.mahallas],
            **_sum([agg.get(pc.id, _sum([]))]),
        })
    return {"level": "district", "id": d.id, "name": d.name, "children": children, "subject": subject,
            "subject_counts": _subject_counts(db, _visible_polyclinics(db, user, [d])),
            "breadcrumb": [{"level": "country", "name": "O'zbekiston"}, {"level": "region", "id": d.region_id, "name": d.region.name}]}


@router.get("/geo/polyclinics/search")
def search_polyclinics(q: str = "", subject: str = SubjectQ, _: User = Depends(current_user),
                       db: Session = Depends(get_db)) -> list[dict]:
    """Search polyclinics and mahallas (accent-insensitive). Returns AGGREGATES ONLY — works for every role."""
    agg = _counts_by_polyclinic(db, subject)
    m_agg = _counts_by_mahalla(db, subject)
    out = []
    for pc in db.scalars(select(Polyclinic).order_by(Polyclinic.id)).all():
        m_names = [m.name for m in pc.mahallas]
        if not matches_uz(q, pc.name, pc.code, pc.district.name, pc.district.region.name, *m_names):
            continue
        mahallas = [
            {
                "id": m.id, "name": m.name, "boundary": m.boundary_geojson,
                "centroid": [m.centroid_lat, m.centroid_lon],
                **_sum([m_agg.get(m.id, _sum([]))]),
            }
            for m in pc.mahallas
        ]
        out.append({
            "id": pc.id, "code": pc.code, "name": pc.name, "city": pc.district.name,
            "region_name": pc.district.region.name, "lat": pc.lat, "lon": pc.lon,
            "mahalla_count": len(mahallas), "mahallas": mahallas,
            **_sum([agg.get(pc.id, _sum([]))]),
        })
    return out


@router.get("/geo/polyclinics/{polyclinic_id}")
def geo_polyclinic(polyclinic_id: int, subject: str = SubjectQ, user: User = Depends(require_admin),
                   db: Session = Depends(get_db)) -> dict:
    pc = db.get(Polyclinic, polyclinic_id)
    if pc is None or not _can_see_district(user, pc.district):
        raise HTTPException(404, "Topilmadi")
    agg = _counts_by_polyclinic(db, subject)
    m_agg = _counts_by_mahalla(db, subject)
    mahallas = [{"id": m.id, "name": m.name, "boundary": m.boundary_geojson, **_sum([m_agg.get(m.id, _sum([]))])}
                for m in pc.mahallas]
    return {"level": "polyclinic", "id": pc.id, "code": pc.code, "name": pc.name, "lat": pc.lat, "lon": pc.lon,
            "territory": mahallas, "mahallas": mahallas,
            **_sum([agg.get(pc.id, _sum([]))]), "subject": subject,
            "subject_counts": _subject_counts(db, [pc.id]),
            "breadcrumb": [{"level": "country", "name": "O'zbekiston"},
                           {"level": "region", "id": pc.district.region_id, "name": pc.district.region.name},
                           {"level": "district", "id": pc.district_id, "name": pc.district.name}]}
