"""Task 09 tests:
- Part B: Samarqand polyclinic (PL-SAM-003) with 3 adjacent mahallas, per-mahalla nurses & filter, admin aggregates.
- Part C: Accent-insensitive polyclinic & mahalla search (/api/geo/polyclinics/search), aggregate-only privacy.
- Part A: Responsibility follows mahalla, keyed PINFL hash, rate-limited external lookup, external visit/check entry.
"""
import json

import pytest
from shapely.geometry import shape
from sqlalchemy import select

from app.db import SessionLocal
from app.models import AuditLog, Newborn, NewbornCheck, Patient, Polyclinic, Pregnancy, User
from app.security.crypto import decrypt
from app.services.geo import assign_patient_mahalla, check_patient_polyclinic, decrypt_home, is_inside
from tests.conftest import FRG, NUK, SAM, login


# ---------------- Part B: Samarqand polyclinic with 3 mahallas ----------------
def test_samarqand_three_mahallas_non_overlapping_and_homes_inside(client):
    with SessionLocal() as db:
        pc = db.scalars(select(Polyclinic).where(Polyclinic.code == SAM)).one()
        assert pc.name == "Samarqand shahar 3-son oilaviy poliklinikasi"
        mahallas = list(pc.mahallas)
        assert len(mahallas) == 3
        polys = [shape(m.boundary_geojson) for m in mahallas]
        for i in range(3):
            assert polys[i].is_valid and polys[i].geom_type == "Polygon"
            for j in range(i + 1, 3):
                assert polys[i].intersection(polys[j]).area < 1e-10
        for m in mahallas:
            pats = db.scalars(select(Patient).where(Patient.mahalla_id == m.id)).all()
            assert len(pats) >= 16
            others = [o for o in mahallas if o.id != m.id]
            for p in pats:
                lat, lon = decrypt_home(p.home_enc)
                assert is_inside(m.boundary_geojson, lat, lon), p.code
                assert not any(is_inside(o.boundary_geojson, lat, lon) for o in others)
                assert p.polyclinic_id == pc.id == m.polyclinic_id


def test_samarqand_nurses_see_own_mahalla_by_default_and_all_with_filter(client):
    h1 = login(client, SAM, "nurse")
    h2 = login(client, SAM, "nurse2")
    h3 = login(client, SAM, "nurse3")
    h_doc = login(client, SAM, "doctor")

    me1 = client.get("/api/auth/me", headers=h1).json()
    me2 = client.get("/api/auth/me", headers=h2).json()
    me3 = client.get("/api/auth/me", headers=h3).json()
    assert len({me1["mahalla_id"], me2["mahalla_id"], me3["mahalla_id"]}) == 3

    p1 = client.get("/api/patients", headers=h1).json()
    p2 = client.get("/api/patients", headers=h2).json()
    p3 = client.get("/api/patients", headers=h3).json()
    assert p1 and all(r["mahalla_id"] == me1["mahalla_id"] for r in p1)
    assert p2 and all(r["mahalla_id"] == me2["mahalla_id"] for r in p2)
    assert p3 and all(r["mahalla_id"] == me3["mahalla_id"] for r in p3)
    assert not ({r["patient_id"] for r in p1} & {r["patient_id"] for r in p2})

    # "Barcha mahallalar" filter (all_mahallas=true) returns all 3 mahallas' patients, matching the doctor's view
    p_all = client.get("/api/patients?all_mahallas=true", headers=h1).json()
    p_doc = client.get("/api/patients", headers=h_doc).json()
    assert len(p_all) == len(p1) + len(p2) + len(p3) == len(p_doc)

    # Same for children
    c1 = client.get("/api/children", headers=h1).json()
    c2 = client.get("/api/children", headers=h2).json()
    c3 = client.get("/api/children", headers=h3).json()
    c_all = client.get("/api/children?all_mahallas=true", headers=h1).json()
    assert all(r["mahalla_id"] == me1["mahalla_id"] for r in c1)
    assert len(c_all) == len(c1) + len(c2) + len(c3)


def test_samarqand_map_and_admin_drilldown_counts_add_up(client):
    m_data = client.get("/api/polyclinic/map", headers=login(client, SAM, "doctor")).json()
    assert len(m_data["mahallas"]) == 3
    assert sum(m["total"] for m in m_data["mahallas"]) == sum(1 for p in m_data["points"] if p["kind"] == "pregnancy")

    h_reg = login(client, None, "sam.region.admin")
    h_dist = login(client, None, "sam.district.admin")
    with SessionLocal() as db:
        pc = db.scalars(select(Polyclinic).where(Polyclinic.code == SAM)).one()
        reg_id, dist_id, pc_id = pc.district.region_id, pc.district_id, pc.id

    reg = client.get(f"/api/geo/regions/{reg_id}", headers=h_reg).json()
    dist = client.get(f"/api/geo/districts/{dist_id}", headers=h_dist).json()
    poly = client.get(f"/api/geo/polyclinics/{pc_id}", headers=h_dist).json()

    assert len(poly["mahallas"]) == 3
    assert sum(m["total"] for m in poly["mahallas"]) == poly["total"]
    assert sum(m["red"] for m in poly["mahallas"]) == poly["red"]
    assert dist["children"][0]["total"] == poly["total"]
    assert sum(d.get("total", 0) for d in reg["children"]) == poly["total"]


# ---------------- Part C: Polyclinic search panel & endpoint ----------------
def test_polyclinic_search_accent_insensitive_and_privacy(client):
    for headers in (login(client, SAM, "doctor"), login(client, None, "region.admin")):
        all_pcs = client.get("/api/geo/polyclinics/search", headers=headers).json()
        assert len(all_pcs) == 4

        # Search by city / code / polyclinic name
        nuk = client.get("/api/geo/polyclinics/search?q=Nukus", headers=headers).json()
        assert [p["code"] for p in nuk] == [NUK]
        sam = client.get("/api/geo/polyclinics/search?q=PL-SAM-003", headers=headers).json()
        assert [p["code"] for p in sam] == [SAM] and sam[0]["mahalla_count"] == 3

        # Accent-insensitive matching: o‘ / o' / oʻ and g‘ / g' / gʻ
        for variant in ("Farg'ona", "Farg‘ona", "Fargʻona", "Fargona", "Ma'rifat", "Ma‘rifat", "Maʻrifat"):
            res = client.get("/api/geo/polyclinics/search", params={"q": variant}, headers=headers).json()
            assert [p["code"] for p in res] == [FRG], variant

        for variant in ("Bog'ishamol", "Bog‘ishamol", "Bogʻishamol", "Bogishamol", "Registon", "Siyob"):
            res = client.get("/api/geo/polyclinics/search", params={"q": variant}, headers=headers).json()
            assert [p["code"] for p in res] == [SAM], variant

        # Subject switch changes counts
        child_res = client.get("/api/geo/polyclinics/search?q=Samarqand&subject=child", headers=headers).json()
        all_res = client.get("/api/geo/polyclinics/search?q=Samarqand&subject=all", headers=headers).json()
        assert all_res[0]["total"] == sam[0]["total"] + child_res[0]["total"]

        # Privacy check: no patient codes, names, PINFL, hashes or home points
        raw = json.dumps(all_pcs, ensure_ascii=False)
        for forbidden in ("QQR-NUK-", "TSH-CHL-", "FAR-FRG-", "SAM-SAM-", "pinfl", "full_name", "phone", "points", "home"):
            assert forbidden not in raw


# ---------------- Part A: Responsibility follows mahalla & External entry ----------------
def test_patient_polyclinic_always_follows_mahalla(client):
    with SessionLocal() as db:
        sam_pc = db.scalars(select(Polyclinic).where(Polyclinic.code == SAM)).one()
        nuk_pc = db.scalars(select(Polyclinic).where(Polyclinic.code == NUK)).one()
        sam_m = sam_pc.mahallas[0]
        nuk_m = nuk_pc.mahallas[0]

        pat = db.scalars(select(Patient).where(Patient.mahalla_id == sam_m.id)).first()
        assert pat.polyclinic_id == sam_pc.id
        check_patient_polyclinic(db, pat)

        # Move patient to Nukus mahalla -> polyclinic_id (and any children) follow the mahalla
        assign_patient_mahalla(db, pat, nuk_m)
        db.flush()
        assert pat.polyclinic_id == nuk_pc.id
        for pr in pat.pregnancies:
            for nb in pr.newborns:
                assert nb.polyclinic_id == nuk_pc.id and nb.mahalla_id == nuk_m.id

        # Move back to Samarqand mahalla
        assign_patient_mahalla(db, pat, sam_m)
        db.commit()
        assert pat.polyclinic_id == sam_pc.id

        # Service check catches manual mismatch before flush
        pat.polyclinic_id = nuk_pc.id
        with pytest.raises(ValueError, match="mos emas"):
            check_patient_polyclinic(db, pat)
        # Flushing automatically heals patient.polyclinic_id back to sam_m.polyclinic_id
        db.flush()
        assert pat.polyclinic_id == sam_pc.id
        db.rollback()


def test_pinfl_hash_populated_and_never_in_api_output(client):
    with SessionLocal() as db:
        pats = db.scalars(select(Patient)).all()
        assert pats and all(p.pinfl_hash and len(p.pinfl_hash) == 64 for p in pats)
        sample = pats[0]
        h_val = sample.pinfl_hash
        pid = sample.id

    h = login(client, NUK, "nurse")
    for path, method in [("/api/patients", "GET"), (f"/api/patients/{pid}", "GET"), (f"/api/patients/{pid}/reveal", "POST")]:
        txt = client.request(method, path, headers=h).text
        assert "pinfl_hash" not in txt and h_val not in txt


def test_external_lookup_and_visit_lands_in_responsible_clinic(client):
    from app.services import notify

    notify.OUTBOX.clear()
    with SessionLocal() as db:
        sam_pc = db.scalars(select(Polyclinic).where(Polyclinic.code == SAM)).one()
        nuk_pc = db.scalars(select(Polyclinic).where(Polyclinic.code == NUK)).one()
        # Pick an active green/yellow pregnancy in Samarqand so a severe BP visit triggers a RED alert
        preg = db.scalars(
            select(Pregnancy).join(Patient).where(
                Patient.polyclinic_id == sam_pc.id,
                Pregnancy.status == "active",
                Pregnancy.current_zone.in_(("green", "yellow")),
            )
        ).first()
        assert preg is not None
        pat = preg.patient
        sam_pid, sam_preg_id, sam_code = pat.id, preg.id, pat.code
        sam_pinfl = decrypt(pat.pinfl_enc)
        sam_name = decrypt(pat.full_name_enc)
        sam_pc_id, nuk_pc_id = sam_pc.id, nuk_pc.id

    h_nuk = login(client, NUK, "nurse")

    # 1. Wrong JShShIR -> 404 without revealing anything, logged as external_lookup_miss
    miss = client.post("/api/external/lookup", json={"pinfl": "00000000000000"}, headers=h_nuk)
    assert miss.status_code == 404 and miss.json() == {"detail": "Topilmadi"}

    # 2. Exact JShShIR lookup -> minimum necessary only (NO name, zone, history, address, or hash)
    lk = client.post("/api/external/lookup", json={"pinfl": sam_pinfl}, headers=h_nuk)
    assert lk.status_code == 200, lk.text
    lk_body = lk.json()
    assert lk_body["patient_code"] == sam_code
    assert lk_body["responsible_polyclinic_code"] == SAM
    assert lk_body["responsible_polyclinic_name"] == "Samarqand shahar 3-son oilaviy poliklinikasi"
    assert lk_body["has_active_pregnancy"] is True
    raw_lk = json.dumps(lk_body, ensure_ascii=False)
    for forbidden in (sam_name, sam_pinfl, "zone", "history", "home", "pinfl_hash", "full_name"):
        assert forbidden not in raw_lk

    # 3. External nurse records a high-BP visit for the Samarqand woman
    ext = client.post("/api/external/visits", headers=h_nuk, json={
        "pinfl": sam_pinfl,
        "systolic": 168,
        "diastolic": 112,
        "proteinuria": "+2",
        "hemoglobin_g_l": 102,
        "symptoms": ["severe_headache"],
        "notes": "Nukusda tahlil topshirildi",
    })
    assert ext.status_code == 201, ext.text
    ext_body = ext.json()
    assert ext_body["message_uz"] == "Natija mas'ul poliklinikaga yuborildi: Samarqand shahar 3-son oilaviy poliklinikasi"
    assert ext_body["responsible_polyclinic_id"] == sam_pc_id
    assert ext_body["performed_at_polyclinic_id"] == nuk_pc_id
    assert "zone" not in ext_body and sam_name not in json.dumps(ext_body)

    # 4. External user STILL cannot read the patient card or pregnancy afterwards (404)
    assert client.get(f"/api/patients/{sam_pid}", headers=h_nuk).status_code == 404
    assert client.get(f"/api/llm/summary/{sam_preg_id}", headers=h_nuk).status_code == 404

    # 5. Responsible clinic (Samarqand) sees the visit with the badge + notification + alert
    h_sam_doc = login(client, SAM, "doctor")
    card = client.get(f"/api/patients/{sam_pid}", headers=h_sam_doc).json()
    last_v = card["visits"][-1]
    assert last_v["performed_at_polyclinic_id"] == nuk_pc_id
    assert last_v["performed_at_polyclinic_name"] == "Nukus shahar 1-son oilaviy poliklinikasi"
    assert last_v["external_badge_uz"] == "Boshqa poliklinikada o'tkazilgan: Nukus shahar 1-son oilaviy poliklinikasi"
    assert card["pregnancy"]["current_zone"] == "red"

    notifs = client.get("/api/external/notifications", headers=h_sam_doc).json()
    assert any(n["id"] == last_v["id"] and n["notice_uz"] == "Tashqi natija kelib tushdi" for n in notifs)

    # Alert went to Samarqand specialist, NOT Nukus specialist
    sam_alerts = client.get("/api/alerts?status=active", headers=login(client, SAM, "specialist")).json()
    nuk_alerts = client.get("/api/alerts?status=active", headers=login(client, NUK, "specialist")).json()
    sam_alert = next((a for a in sam_alerts if a["pregnancy_id"] == sam_preg_id), None)
    assert sam_alert is not None and sam_alert["level"] == "red"
    assert sam_alert["performed_at_polyclinic_name"] == "Nukus shahar 1-son oilaviy poliklinikasi"
    assert sam_alert["external_notice_uz"] == "Tashqi natija kelib tushdi"
    assert not any(a["pregnancy_id"] == sam_preg_id for a in nuk_alerts)

    # 6. Audit log has external_lookup_miss, external_lookup, and external_entry with both polyclinic IDs
    with SessionLocal() as db:
        entry_log = db.scalars(
            select(AuditLog).where(AuditLog.action == "external_entry", AuditLog.entity_id == last_v["id"])
        ).one()
        assert entry_log.from_polyclinic_id == nuk_pc_id and entry_log.to_polyclinic_id == sam_pc_id
        assert db.scalars(select(AuditLog).where(AuditLog.action == "external_lookup", AuditLog.entity_id == sam_pid)).first()
        assert db.scalars(select(AuditLog).where(AuditLog.action == "external_lookup_miss")).first()


def test_external_child_check_and_rate_limit(client):
    with SessionLocal() as db:
        sam_pc = db.scalars(select(Polyclinic).where(Polyclinic.code == SAM)).one()
        nuk_pc = db.scalars(select(Polyclinic).where(Polyclinic.code == NUK)).one()
        nb = db.scalars(select(Newborn).where(Newborn.polyclinic_id == sam_pc.id, Newborn.status == "active")).first()
        assert nb is not None
        pinfl = decrypt(nb.pregnancy.patient.pinfl_enc)
        nb_id = nb.id
        nuk_user = db.scalars(select(User).where(User.polyclinic_id == nuk_pc.id, User.username == "doctor")).one()
        nuk_uid = nuk_user.id

    h_nuk_doc = login(client, NUK, "doctor")
    r = client.post("/api/external/checks", headers=h_nuk_doc, json={
        "pinfl": pinfl, "newborn_id": nb_id, "resp_rate": 42, "temperature_c": 36.7, "weight_g": 6200,
    })
    assert r.status_code == 201, r.text
    assert r.json()["performed_at_polyclinic_id"] == nuk_pc.id
    with SessionLocal() as db:
        ck = db.get(NewbornCheck, r.json()["id"])
        assert ck.performed_at_polyclinic_id == nuk_pc.id and ck.entered_by == nuk_uid

    # Rate limit: 30 lookups/hour per user
    with SessionLocal() as db:
        for _ in range(30):
            db.add(AuditLog(user_id=nuk_uid, action="external_lookup_miss", entity="patient"))
        db.commit()
    limited = client.post("/api/external/lookup", json={"pinfl": pinfl}, headers=h_nuk_doc)
    assert limited.status_code == 429
