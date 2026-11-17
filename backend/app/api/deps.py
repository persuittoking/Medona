"""Auth, role scope and audit dependencies."""
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AuditLog, District, Patient, Pregnancy, User
from app.security.auth import decode_token

bearer = HTTPBearer(auto_error=False)


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    uid = decode_token(creds.credentials) if creds else None
    user = db.get(User, uid) if uid else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Tizimga kirish talab qilinadi")
    return user


def require_roles(*roles: str):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Ruxsat yo'q")
        return user
    return dep


def scope_patients(stmt: Select, user: User) -> Select:
    """Restrict a query that already joins Patient to the user's scope."""
    if user.role == "nurse":
        return stmt.where(Patient.assigned_nurse_id == user.id)
    if user.role in ("doctor", "specialist"):
        return stmt.where(Patient.district_id == user.district_id)
    return stmt.where(Patient.district_id.in_(select(District.id).where(District.region_id == user.region_id)))


def can_access_patient(user: User, patient: Patient) -> bool:
    if user.role == "nurse":
        return patient.assigned_nurse_id == user.id
    if user.role in ("doctor", "specialist"):
        return patient.district_id == user.district_id
    return patient.district.region_id == user.region_id


def get_pregnancy_checked(db: Session, pregnancy_id: int, user: User) -> Pregnancy:
    preg = db.get(Pregnancy, pregnancy_id)
    if preg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Homiladorlik topilmadi")
    if not can_access_patient(user, preg.patient):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu bemor sizning hududingizga tegishli emas")
    return preg


def audit(db: Session, user: User | None, action: str, entity: str, entity_id: int | None,
          request: Request | None = None) -> None:
    ip = request.client.host if request is not None and request.client else None
    db.add(AuditLog(user_id=user.id if user else None, action=action, entity=entity, entity_id=entity_id, ip=ip))
