"""FastAPI 依赖：当前用户、写权限、数据范围。"""

from __future__ import annotations

import datetime

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import security
from app.config import get_settings
from app.database import get_db
from app.models import AuthSession, User

bearer_scheme = HTTPBearer(auto_error=False)


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")

    token_hash = security.hash_token(credentials.credentials)
    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash))
    if session is None or session.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已失效")

    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=datetime.timezone.utc)
    if expires_at <= utcnow():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已过期")

    user = db.get(User, session.user_id)
    if user is None or user.is_deleted or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号不可用")
    return user


def require_write(current_user: User = Depends(get_current_user)) -> User:
    if not security.can_write(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="没有修改权限")
    return current_user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if not security.can_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return current_user


def session_ttl_minutes() -> int:
    return get_settings().session_ttl_minutes
