"""Point-in-polygon validation and home points of the seeded patients."""
import numpy as np
import pytest

from app.db import SessionLocal
from app.models import Patient
from app.services.geo import OutsideMahalla, decrypt_home, is_inside, sample_points, validate_home

SQUARE = {"type": "Polygon", "coordinates": [[[59.60, 42.45], [59.62, 42.45], [59.62, 42.47], [59.60, 42.47], [59.60, 42.45]]]}


@pytest.mark.parametrize("lat,lon,inside", [
    (42.46, 59.61, True),      # centre
    (42.45, 59.61, True),      # on the border counts as inside
    (42.44, 59.61, False),     # south of it
    (42.46, 59.63, False),     # east of it
    (59.61, 42.46, False),     # lat/lon swapped
])
def test_point_in_polygon(lat, lon, inside):
    assert is_inside(SQUARE, lat, lon) is inside


def test_validate_home_raises_outside():
    validate_home(SQUARE, 42.46, 59.61)
    with pytest.raises(OutsideMahalla):
        validate_home(SQUARE, 42.40, 59.61)


def test_sampled_points_are_inside():
    pts = sample_points(SQUARE, 200, np.random.default_rng(1))
    assert len(pts) == 200 and all(is_inside(SQUARE, lat, lon) for lat, lon in pts)


def test_every_seeded_home_is_inside_its_mahalla(client):
    with SessionLocal() as db:
        patients = db.query(Patient).all()
        assert patients
        for p in patients:
            lat, lon = decrypt_home(p.home_enc)
            assert is_inside(p.mahalla.boundary_geojson, lat, lon), p.code
            assert p.mahalla.polyclinic_id == p.polyclinic_id
            assert str(lat) not in p.home_enc  # stored encrypted


def test_home_point_visible_to_own_polyclinic_only(client):
    from tests.conftest import CHL, NUK, demo, login

    pid, _ = demo()
    own = client.get(f"/api/patients/{pid}", headers=login(client, NUK, "nurse")).json()
    assert set(own["home"]) == {"lat", "lon"}
    assert client.get(f"/api/patients/{pid}", headers=login(client, CHL, "nurse")).status_code == 404
    m = client.get("/api/polyclinic/map", headers=login(client, NUK, "nurse")).json()
    assert any(pt["patient_id"] == pid for pt in m["points"]) and m["mahallas"][0]["boundary"]["type"] == "Polygon"


def test_public_territories_have_no_patient_data(client):
    terr = client.get("/api/public/territories").json()
    assert len(terr) == 3
    text = str(terr)
    for forbidden in ("patient", "points", "lat\": ", "red", "zone", "QQR-NUK-"):
        assert forbidden not in text
