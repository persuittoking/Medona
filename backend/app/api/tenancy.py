"""TENANT ISOLATION — the single place where patient-level access is decided.

Every patient / pregnancy / visit / child / alert / AI-summary / home-point query goes through `Tenant`:
- polyclinic staff (nurse, doctor, specialist) see ONLY rows whose Patient.polyclinic_id equals theirs;
- another tenant's ids return 404 (we do not reveal that the record exists);
- admin roles (district_admin, region_admin) get 403 on every patient-level endpoint — they only use
  the aggregate endpoints in app/api/geo.py.
"""
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from sqlalchemy import Select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.models import POLYCLINIC_ROLES, Alert, Newborn, Patient, Pregnancy, User

NOT_FOUND = "Topilmadi"


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
