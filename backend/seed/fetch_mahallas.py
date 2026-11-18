"""Build mahalla boundary polygons for the 3 demo polyclinics.

1. Try OpenStreetMap administrative boundaries (admin_level 8-11) via Overpass.
2. If none exist (true for all 3 demo areas, checked 2026-11-17), build a DEMO boundary that follows
   REAL streets: download the OSM road network around a real neighbourhood, cut it into street blocks
   (shapely.polygonize) and merge the blocks closest to the neighbourhood centre.

Output: backend/seed/mahallas/<key>.geojson (FeatureCollection with one Polygon feature).
Usage (from backend/):  .venv\\Scripts\\python seed\\fetch_mahallas.py
Road data (c) OpenStreetMap contributors, ODbL.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import httpx
from shapely.geometry import LineString, Point, Polygon, mapping, shape
from shapely.ops import polygonize, unary_union

OUT = Path(__file__).parent / "mahallas"
CACHE = Path(__file__).parent / "osm_cache"  # raw OSM street downloads, so boundaries rebuild offline
ENDPOINTS = ["https://maps.mail.ru/osm/tools/overpass/api/interpreter", "https://overpass.private.coffee/api/interpreter",
             "https://overpass-api.de/api/interpreter"]

AREAS = {
    "nukus": {"name": "Navbahor MFY", "city": "Nukus shahri", "lat": 42.4605, "lon": 59.6105, "target_km2": 0.55},
    "chilonzor": {"name": "Qatortol MFY", "city": "Chilonzor tumani", "lat": 41.2755, "lon": 69.2045, "target_km2": 0.55},
    "fargona": {"name": "Mustaqillik MFY", "city": "Farg'ona shahri", "lat": 40.3860, "lon": 71.7860, "target_km2": 0.55},
    "samarqand_registon": {
        "name": "Registon MFY", "city": "Samarqand shahri", "lat": 39.6528, "lon": 66.9665,
        "target_km2": 0.45, "group": "samarqand",
    },
    "samarqand_siyob": {
        "name": "Siyob MFY", "city": "Samarqand shahri", "lat": 39.6575, "lon": 66.9665,
        "target_km2": 0.45, "group": "samarqand",
    },
    "samarqand_bogishamol": {
        "name": "Bog'ishamol MFY", "city": "Samarqand shahri", "lat": 39.6550, "lon": 66.9605,
        "target_km2": 0.45, "group": "samarqand",
    },
}


def overpass(query: str) -> dict:
    """POST to Overpass. Public mirrors are often busy (504/429), so retry quickly many times."""
    import time

    last: Exception | None = None
    for _attempt in range(8):
        for url in ENDPOINTS:
            try:
                r = httpx.post(url, data={"data": query}, timeout=120 if "mail.ru" in url else 30)
                r.raise_for_status()
                return r.json()
            except Exception as e:  # noqa: BLE001
                last = e
        time.sleep(4)
    raise RuntimeError(f"Overpass unavailable: {last}")


def bbox(lat: float, lon: float, half_m: float) -> str:
    dlat = half_m / 111_320
    dlon = half_m / (111_320 * math.cos(math.radians(lat)))
    return f"{lat - dlat},{lon - dlon},{lat + dlat},{lon + dlon}"


def km2(poly) -> float:
    lat = poly.centroid.y
    return poly.area * 111.32 * 111.32 * math.cos(math.radians(lat))


def admin_boundary(a: dict) -> dict | None:
    """Real OSM mahalla boundary (admin_level 9-11): the one containing the centre, else the nearest one."""
    q = (f'[out:json][timeout:60];relation["boundary"="administrative"]["admin_level"~"^(9|10|11)$"]'
         f'({bbox(a["lat"], a["lon"], 400)});out geom;')
    centre = Point(a["lon"], a["lat"])
    found = []
    for rel in overpass(q).get("elements", []):
        lines = [LineString([(p["lon"], p["lat"]) for p in m["geometry"]]) for m in rel.get("members", [])
                 if m.get("type") == "way" and m.get("role", "outer") in ("outer", "") and m.get("geometry")]
        polys = list(polygonize(unary_union(lines)))
        if not polys:
            continue
        poly = unary_union(polys)
        if poly.geom_type == "MultiPolygon":
            poly = max(poly.geoms, key=lambda g: g.area)
        if 0.05 < km2(poly) < 5:
            found.append((not poly.contains(centre), poly.centroid.distance(centre), rel, poly))
    if not found:
        return None
    _, _, rel, poly = min(found, key=lambda t: (t[0], t[1]))
    tags = rel.get("tags", {})
    return {"geometry": poly.simplify(0.00002), "demo": False, "name": tags.get("name:uz") or tags.get("name"),
            "source": f"OpenStreetMap relation {rel['id']} (admin_level {tags.get('admin_level')}), (c) OpenStreetMap contributors, ODbL"}


def streets(key: str, a: dict, half_m: float = 600) -> dict:
    cached = CACHE / f"{key}_streets.json"
    if cached.exists():
        return json.loads(cached.read_text(encoding="utf-8"))
    q = (f'[out:json][timeout:50];way["highway"~"^(primary|secondary|tertiary|residential|unclassified|living_street|service)$"]'
         f'({bbox(a["lat"], a["lon"], half_m)});out geom;')
    data = overpass(q)
    CACHE.mkdir(exist_ok=True)
    cached.write_text(json.dumps(data), encoding="utf-8")
    return data


def _blocks_from_streets(data: dict) -> list[Polygon]:
    lines = [LineString([(p["lon"], p["lat"]) for p in w["geometry"]])
             for w in data.get("elements", []) if len(w.get("geometry", [])) >= 2]
    if not lines:
        raise RuntimeError("no streets returned")
    blocks = [b for b in polygonize(unary_union(lines)) if km2(b) < 0.4]  # drop huge outer faces
    if not blocks:
        raise RuntimeError("streets do not form closed blocks")
    return blocks


def street_boundary(key: str, a: dict) -> dict:
    blocks = _blocks_from_streets(streets(key, a))
    centre = Point(a["lon"], a["lat"])
    # Take every real street block within a growing radius of the centre, then close the road gaps
    # between them (buffer out/in by ~15 m) so the outline follows the outer streets.
    close = 15 / 111_320
    for radius_m in range(150, 1200, 25):
        chosen = [b for b in blocks if b.centroid.distance(centre) * 111_320 <= radius_m]
        if not chosen:
            continue
        poly = unary_union(chosen).buffer(close).buffer(-close)
        if poly.geom_type == "MultiPolygon":
            poly = max(poly.geoms, key=lambda g: g.area)
        if km2(poly) >= a["target_km2"]:
            break
    poly = Polygon(poly.exterior).simplify(0.00004).buffer(0)
    return {"geometry": poly, "demo": True,
            "source": "demo chegara: OSM street blocks around a real neighbourhood (road data (c) OpenStreetMap, ODbL)"}


def group_street_boundaries(group: str, members: dict[str, dict]) -> dict[str, dict]:
    """Partition one shared street network into adjacent, non-overlapping mahalla polygons."""
    lat = sum(a["lat"] for a in members.values()) / len(members)
    lon = sum(a["lon"] for a in members.values()) / len(members)
    blocks = _blocks_from_streets(streets(group, {"lat": lat, "lon": lon}, half_m=1100))
    group_centre = Point(lon, lat)
    total_target = sum(a["target_km2"] for a in members.values()) * 1.15
    pool = blocks
    for radius_m in range(300, 1400, 25):
        cand = [b for b in blocks if b.centroid.distance(group_centre) * 111_320 <= radius_m]
        if sum(km2(b) for b in cand) >= total_target:
            pool = cand
            break
    centres = {k: Point(a["lon"], a["lat"]) for k, a in members.items()}
    owned: dict[str, list[Polygon]] = {k: [] for k in members}
    for b in pool:
        nearest = min(centres, key=lambda k: b.centroid.distance(centres[k]))
        owned[nearest].append(b)
    close = 24 / 111_320
    prior = Polygon()
    out: dict[str, dict] = {}
    for k in members:
        poly = unary_union(owned[k]).buffer(close).buffer(-close * 0.45)
        if poly.geom_type == "MultiPolygon":
            poly = max(poly.geoms, key=lambda g: g.area)
        poly = Polygon(poly.exterior).simplify(0.00003).buffer(0)
        if not prior.is_empty:
            poly = poly.difference(prior)
            if poly.geom_type == "MultiPolygon":
                poly = max(poly.geoms, key=lambda g: g.area)
            poly = Polygon(poly.exterior).buffer(0)
        prior = unary_union([prior, poly]) if not prior.is_empty else poly
        out[k] = {
            "geometry": poly, "demo": True,
            "source": "demo chegara: OSM street blocks around a real neighbourhood (road data (c) OpenStreetMap, ODbL)",
        }
    return out


def _save_feature(key: str, a: dict, res: dict) -> None:
    poly = res["geometry"]
    name = res.get("name") or a["name"]
    fc = {"type": "FeatureCollection", "features": [{
        "type": "Feature", "geometry": mapping(poly),
        "properties": {"key": key, "name": name, "city": a["city"], "demo_boundary": res["demo"],
                       "source": res["source"], "area_km2": round(km2(poly), 3)},
    }]}
    (OUT / f"{key}.geojson").write_text(json.dumps(fc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{key}: {name} — {km2(poly):.2f} km², {len(poly.exterior.coords)} vertices — {res['source']}")


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=list(AREAS))
    ap.add_argument("--skip-admin", action="store_true", help="skip the official-boundary check (already done)")
    args = ap.parse_args()
    keys = set(args.only)
    OUT.mkdir(parents=True, exist_ok=True)
    done_groups: set[str] = set()
    for key, a in AREAS.items():
        if key not in keys:
            continue
        grp = a.get("group")
        if grp:
            if grp in done_groups:
                continue
            done_groups.add(grp)
            members = {k: v for k, v in AREAS.items() if v.get("group") == grp}
            built = group_street_boundaries(grp, members)
            for mk, mres in built.items():
                if mk in keys:
                    _save_feature(mk, members[mk], mres)
            continue
        try:
            official = None if args.skip_admin else admin_boundary(a)
        except RuntimeError as e:  # Overpass down: record it and fall back to the street-based demo boundary
            print(f"{key}: admin boundary check failed ({e}); using street blocks")
            official = None
        res = official or street_boundary(key, a)
        _save_feature(key, a, res)


if __name__ == "__main__":
    main()


def load(key: str) -> dict:
    """Read a saved boundary feature (used by the seed)."""
    return json.loads((OUT / f"{key}.geojson").read_text(encoding="utf-8"))["features"][0]


def as_shape(feature: dict):
    return shape(feature["geometry"])
