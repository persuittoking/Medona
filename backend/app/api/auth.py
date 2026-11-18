from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import audit, current_user
from app.db import get_db
from app.models import ADMIN_ROLES, District, Mahalla, Polyclinic, Region, User
from app.schemas import LoginIn, TokenOut, UserOut
from app.security.auth import create_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])
BAD_LOGIN = "Poliklinika ID, login yoki parol noto'g'ri"


def user_out(db: Session, u: User) -> UserOut:
    out = UserOut.model_validate(u)
    if u.polyclinic_id:
        pc = db.get(Polyclinic, u.polyclinic_id)
        out.polyclinic_code, out.polyclinic_name = pc.code, pc.name
    if u.mahalla_id:
        m = db.get(Mahalla, u.mahalla_id)
        out.mahalla_name = m.name if m else None
    if u.district_id:
        out.district_name = db.get(District, u.district_id).name
    if u.region_id:
        out.region_name = db.get(Region, u.region_id).name
    return out


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)) -> TokenOut:
    username = body.username.strip().lower()
    code = (body.polyclinic_code or "").strip().upper()
    if code:
        pc = db.scalars(select(Polyclinic).where(Polyclinic.code == code)).first()
        user = db.scalars(select(User).where(User.polyclinic_id == pc.id, User.username == username)).first() if pc else None
    else:  # district / region admins log in without a polyclinic ID
        user = db.scalars(select(User).where(User.polyclinic_id.is_(None), User.username == username,
                                             User.role.in_(ADMIN_ROLES))).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, BAD_LOGIN)
    audit(db, user, "login", "user", user.id, request)
    db.commit()
    return TokenOut(access_token=create_token(user.id, user.role), user=user_out(db, user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user), db: Session = Depends(get_db)) -> UserOut:
    return user_out(db, user)
