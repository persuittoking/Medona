from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import audit, current_user
from app.db import get_db
from app.models import District, Region, User
from app.schemas import LoginIn, TokenOut, UserOut
from app.security.auth import create_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def user_out(db: Session, u: User) -> UserOut:
    out = UserOut.model_validate(u)
    if u.district_id:
        out.district_name = db.get(District, u.district_id).name
    if u.region_id:
        out.region_name = db.get(Region, u.region_id).name
    return out


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)) -> TokenOut:
    user = db.scalars(select(User).where(User.username == body.username.strip().lower())).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Login yoki parol noto'g'ri")
    audit(db, user, "login", "user", user.id, request)
    db.commit()
    return TokenOut(access_token=create_token(user.id, user.role), user=user_out(db, user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user), db: Session = Depends(get_db)) -> UserOut:
    return user_out(db, user)
