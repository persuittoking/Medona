"""Proof-of-care endpoints outside the alert card: quality signals (department head) and patient transfer."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select

from app.api.deps import audit
from app.api.tenancy import Tenant, staff
from app.models import Mahalla, Polyclinic
from app.schemas import TransferIn
from app.services.closed_loop import transfer_patient
from app.services.quality import SIGNAL_LABEL_UZ, loop_tiles, quality_report

router = APIRouter(prefix="/api", tags=["proof-of-care"])


@router.get("/quality")
def quality(request: Request, t: Tenant = Depends(staff("department_head"))) -> dict:
    """"Sifat nazorati": plausibility signals per user (counts + patient codes only). Department head only."""
    users = quality_report(t.db, t.polyclinic_id)
    audit(t.db, t.user, "view_quality", "polyclinic", t.polyclinic_id, request)
    t.db.commit()
    return {"label_uz": SIGNAL_LABEL_UZ, "tiles": loop_tiles(t.db, t.polyclinic_id), "users": users,
            "synthetic": True}


@router.get("/quality/tiles")
def quality_tiles(t: Tenant = Depends(staff("department_head"))) -> dict:
    return loop_tiles(t.db, t.polyclinic_id)


@router.get("/transfer/mahallas")
def transfer_targets(t: Tenant = Depends(staff("nurse", "doctor"))) -> list[dict]:
    """Mahallas of every polyclinic (names only, no counts) for "moved permanently"."""
    rows = t.db.execute(select(Mahalla, Polyclinic).join(Polyclinic, Mahalla.polyclinic_id == Polyclinic.id)
                        .order_by(Polyclinic.code, Mahalla.name)).all()
    return [{"id": m.id, "name": m.name, "polyclinic_code": pc.code, "polyclinic_name": pc.name,
             "own": pc.id == t.polyclinic_id} for m, pc in rows]


@router.post("/patients/{patient_id}/transfer")
def transfer(patient_id: int, body: TransferIn, request: Request, t: Tenant = Depends(staff("nurse", "doctor"))) -> dict:
    """She moved permanently: responsibility follows the new mahalla (both polyclinics audit-logged)."""
    pat = t.get_patient(patient_id)
    target = t.db.get(Mahalla, body.mahalla_id)
    if target is None:
        raise HTTPException(404, "Mahalla topilmadi")
    if target.id == pat.mahalla_id:
        raise HTTPException(409, "Bemor allaqachon shu mahallada")
    ip = request.client.host if request.client else None
    moved = transfer_patient(t.db, pat, target, t.user, ip)
    t.db.commit()
    return {"patient_code": pat.code, "mahalla_name": target.name, "polyclinic_code": target.polyclinic.code,
            "polyclinic_name": target.polyclinic.name, "alerts_moved": moved,
            "message_uz": f"Bemor {target.polyclinic.name} ({target.name}) mas'uliyatiga o'tkazildi"}
