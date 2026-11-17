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
        for x, y in zip(xs, ys):
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
