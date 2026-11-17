"""Auth and audit dependencies. Patient-level scoping lives ONLY in app/api/tenancy.py."""
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ADMIN_ROLES, AuditLog, User
from app.security.auth import decode_token

bearer = HTTPBearer(auto_error=False)


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    uid = decode_token(creds.credentials) if creds else None
    user = db.get(User, uid) if uid else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Tizimga kirish talab qilinadi")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role not in ADMIN_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Faqat tuman/viloyat boshqaruvi uchun")
    return user


def audit(db: Session, user: User | None, action: str, entity: str, entity_id: int | None,
          request: Request | None = None) -> None:
    ip = request.client.host if request is not None and request.client else None
    db.add(AuditLog(user_id=user.id if user else None, action=action, entity=entity, entity_id=entity_id, ip=ip))
