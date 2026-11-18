"""Mahalla geometry helpers (shapely): point-in-polygon validation, sampling, home-point crypto."""
from __future__ import annotations

import numpy as np
from shapely.geometry import Point, shape
from shapely.prepared import prep

from app.security.crypto import decrypt, encrypt


class OutsideMahalla(ValueError):
    pass


def polygon(boundary_geojson: dict):
    return shape(boundary_geojson)


def is_inside(boundary_geojson: dict, lat: float, lon: float) -> bool:
    """True if the point is inside the mahalla or on its border (GeoJSON order is lon, lat)."""
    return polygon(boundary_geojson).covers(Point(lon, lat))


def validate_home(boundary_geojson: dict, lat: float, lon: float) -> None:
    if not is_inside(boundary_geojson, lat, lon):
        raise OutsideMahalla("Uy manzili mahalla chegarasidan tashqarida")


def sample_points(boundary_geojson: dict, n: int, rng: np.random.Generator, inset_m: float = 8.0) -> list[tuple[float, float]]:
    """Uniform random (lat, lon) points inside the polygon (rejection sampling), kept a few metres off the border."""
    poly = polygon(boundary_geojson)
    inner = poly.buffer(-inset_m / 111_320) if inset_m else poly
    if inner.is_empty:
        inner = poly
    p = prep(inner)
    minx, miny, maxx, maxy = inner.bounds
    out: list[tuple[float, float]] = []
    while len(out) < n:
        xs, ys = rng.uniform(minx, maxx, n * 3), rng.uniform(miny, maxy, n * 3)
        for x, y in zip(xs, ys, strict=True):
            if p.contains(Point(x, y)):
                out.append((round(float(y), 6), round(float(x), 6)))
                if len(out) == n:
                    break
    return out


def encrypt_home(lat: float, lon: float) -> str:
    return encrypt(f"{lat:.6f},{lon:.6f}")


def decrypt_home(token: str) -> tuple[float, float]:
    lat, lon = decrypt(token).split(",")
    return float(lat), float(lon)


def check_patient_polyclinic(db, patient) -> None:
    """Service check: Patient.polyclinic_id must always equal the polyclinic of Patient.mahalla_id."""
    from app.models import Mahalla

    m = patient.mahalla if patient.mahalla is not None and patient.mahalla.id == patient.mahalla_id else None
    if m is None and patient.mahalla_id is not None:
        m = db.get(Mahalla, patient.mahalla_id)
    if m is None:
        raise ValueError("Mahalla topilmadi")
    if patient.polyclinic_id != m.polyclinic_id:
        raise ValueError("Bemor poliklinikasi mahalla poliklinikasiga mos emas")


def assign_patient_mahalla(db, patient, mahalla) -> None:
    """Set or move a patient's mahalla; responsibility (polyclinic_id) always follows the mahalla."""
    from app.models import Mahalla

    m = db.get(Mahalla, mahalla) if isinstance(mahalla, int) else mahalla
    if m is None:
        raise ValueError("Mahalla topilmadi")
    patient.mahalla = m
    patient.mahalla_id = m.id
    patient.polyclinic_id = m.polyclinic_id
    for pr in patient.pregnancies:
        for nb in pr.newborns:
            nb.mahalla_id = m.id
            nb.polyclinic_id = m.polyclinic_id
    check_patient_polyclinic(db, patient)
