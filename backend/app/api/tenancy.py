"""TENANT ISOLATION — the single place where patient-level access is decided.

Every patient / pregnancy / visit / child / alert / AI-summary / home-point query goes through `Tenant`:
- polyclinic staff (nurse, doctor, specialist) see ONLY rows whose Patient.polyclinic_id equals theirs;
- another tenant's ids return 404 (we do not reveal that the record exists);
- admin roles (district_admin, region_admin) get 403 on every patient-level endpoint — they only use
  the aggregate endpoints in app/api/geo.py.
"""
from dataclasses import dataclass
from datetime import timedelta

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.models import POLYCLINIC_ROLES, Alert, AuditLog, Newborn, Patient, Pregnancy, User, utcnow
from app.security.crypto import hash_pinfl

NOT_FOUND = "Topilmadi"
EXTERNAL_LOOKUP_LIMIT_PER_HOUR = 30


@dataclass
class Tenant:
    user: User
    polyclinic_id: int
    db: Session

    def patients(self, stmt: Select) -> Select:
        """Restrict a statement that already joins Patient to this tenant."""
        return stmt.where(Patient.polyclinic_id == self.polyclinic_id)

    def get_patient(self, patient_id: int) -> Patient:
        pat = self.db.get(Patient, patient_id)
        if pat is None or pat.polyclinic_id != self.polyclinic_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
        return pat

    def get_pregnancy(self, pregnancy_id: int) -> Pregnancy:
        preg = self.db.get(Pregnancy, pregnancy_id)
        if preg is None or preg.patient.polyclinic_id != self.polyclinic_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
        return preg

    def children(self, stmt: Select) -> Select:
        """Restrict a statement over Newborn to this tenant (key copied from the mother's patient record)."""
        return stmt.where(Newborn.polyclinic_id == self.polyclinic_id)

    def alerts(self, stmt: Select) -> Select:
        """Restrict a statement over Alert to this tenant, for both subjects (pregnancy and child)."""
        from app.services.alerts import polyclinic_alerts

        return polyclinic_alerts(stmt, self.polyclinic_id)

    def get_newborn(self, newborn_id: int) -> Newborn:
        nb = self.db.get(Newborn, newborn_id)
        if nb is None or nb.polyclinic_id != self.polyclinic_id or nb.pregnancy.patient.polyclinic_id != self.polyclinic_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
        return nb

    def get_alert(self, alert_id: int) -> Alert:
        a = self.db.get(Alert, alert_id)
        if a is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
        if a.pregnancy is not None:
            ok = a.pregnancy.patient.polyclinic_id == self.polyclinic_id
        elif a.newborn is not None:
            ok = a.newborn.polyclinic_id == self.polyclinic_id
        else:
            ok = False
        if not ok:
            raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
        return a

    def lookup_by_pinfl(self, pinfl: str, request: Request | None = None) -> Patient:
        """Exact-match JShShIR lookup for external result entry (minimum-necessary view, rate-limited, audited)."""
        ip = request.client.host if request is not None and request.client else None
        since = utcnow() - timedelta(hours=1)
        recent = self.db.scalar(
            select(func.count()).select_from(AuditLog).where(
                AuditLog.user_id == self.user.id,
                AuditLog.action.in_(("external_lookup", "external_lookup_miss")),
                AuditLog.created_at >= since,
            )
        ) or 0
        if recent >= EXTERNAL_LOOKUP_LIMIT_PER_HOUR:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                "JShShIR qidiruv limiti tugadi (soatiga 30 ta). Birozdan so'ng qayta urinib ko'ring")
        cleaned = (pinfl or "").strip()
        pat = self.db.scalars(select(Patient).where(Patient.pinfl_hash == hash_pinfl(cleaned))).first() if cleaned else None
        if pat is None:
            self.db.add(AuditLog(user_id=self.user.id, action="external_lookup_miss", entity="patient",
                                 entity_id=None, from_polyclinic_id=self.polyclinic_id, ip=ip))
            self.db.commit()
            raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
        self.db.add(AuditLog(
            user_id=self.user.id, action="external_lookup", entity="patient", entity_id=pat.id,
            from_polyclinic_id=self.polyclinic_id, to_polyclinic_id=pat.polyclinic_id,
            details=f"from_polyclinic_id={self.polyclinic_id},to_polyclinic_id={pat.polyclinic_id}", ip=ip,
        ))
        self.db.commit()
        return pat

    def resolve_external_pregnancy(self, *, pinfl: str | None = None, pregnancy_id: int | None = None,
                                   patient_code: str | None = None) -> Pregnancy:
        """Resolve an active pregnancy for external result entry (stored under the responsible polyclinic)."""
        pat: Patient | None = None
        if pinfl:
            pat = self.db.scalars(select(Patient).where(Patient.pinfl_hash == hash_pinfl(pinfl.strip()))).first()
        elif patient_code:
            pat = self.db.scalars(select(Patient).where(Patient.code == patient_code.strip())).first()
        elif pregnancy_id is not None:
            preg = self.db.get(Pregnancy, pregnancy_id)
            if preg is None or preg.status != "active":
                raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
            return preg
        if pat is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
        active = [pr for pr in pat.pregnancies if pr.status == "active"]
        if not active:
            raise HTTPException(status.HTTP_409_CONFLICT, "Bu bemorda faol homiladorlik topilmadi")
        return sorted(active, key=lambda p: -p.id)[0]

    def resolve_external_newborn(self, *, pinfl: str | None = None, newborn_id: int | None = None,
                                 child_code: str | None = None) -> Newborn:
        """Resolve an active child (0-12m) for external check entry (stored under the responsible polyclinic)."""
        if newborn_id is not None:
            nb = self.db.get(Newborn, newborn_id)
        elif child_code:
            nb = self.db.scalars(select(Newborn).where(Newborn.code == child_code.strip())).first()
        elif pinfl:
            pat = self.db.scalars(select(Patient).where(Patient.pinfl_hash == hash_pinfl(pinfl.strip()))).first()
            nbs = [n for pr in (pat.pregnancies if pat else []) for n in pr.newborns if n.status == "active"]
            nb = sorted(nbs, key=lambda n: -n.id)[0] if nbs else None
        else:
            nb = None
        if nb is None or nb.status != "active":
            raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
        return nb


def staff(*roles: str):
    """Dependency factory: polyclinic staff only (optionally limited to `roles`)."""
    allowed = roles or POLYCLINIC_ROLES

    def dep(user: User = Depends(current_user), db: Session = Depends(get_db)) -> Tenant:
        if user.role not in POLYCLINIC_ROLES or user.polyclinic_id is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Bemor ma'lumotlari faqat poliklinika xodimlari uchun")
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Ruxsat yo'q")
        return Tenant(user=user, polyclinic_id=user.polyclinic_id, db=db)

    return dep
