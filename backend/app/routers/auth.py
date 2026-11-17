"""认证接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import security
from app.database import get_db
from app.deps import bearer_scheme, get_current_user, session_ttl_minutes, utcnow
from app.models import AuthSession, User
from app.schemas import LoginIn, TokenOut, UserOut
from app.services import write_audit

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, request: Request, db: Session = Depends(get_db)) -> TokenOut:
    user = db.scalar(select(User).where(User.username == payload.username, User.is_deleted.is_(False)))
    # 统一提示，避免通过错误信息枚举账号。
    if user is None or not user.is_active or not security.verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码错误")

    token, token_hash = security.new_session_token()
    expires_at = security.session_expiry(utcnow(), session_ttl_minutes())
    db.add(AuthSession(user_id=user.id, token_hash=token_hash, expires_at=expires_at))
    write_audit(
        db, user=user, action="login", object_type="user", object_id=user.id, summary="登录成功", request=request
    )
    db.commit()
    return TokenOut(access_token=token, expires_at=expires_at, user=UserOut.model_validate(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> None:
    now = utcnow()
    if credentials is not None and credentials.credentials:
        token_hash = security.hash_token(credentials.credentials)
        session = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash))
        if session is not None and session.revoked_at is None:
            session.revoked_at = now
    write_audit(
        db,
        user=current_user,
        action="logout",
        object_type="user",
        object_id=current_user.id,
        summary="退出当前会话",
        request=request,
    )
    db.commit()


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current_user)
