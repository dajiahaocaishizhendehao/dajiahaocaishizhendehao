"""密码哈希、会话令牌与权限判断。

密码使用标准库 PBKDF2-HMAC-SHA256，避免引入额外依赖；参数随哈希一起保存，
便于将来提高迭代次数后平滑升级。令牌原文不落库，只保存 SHA-256 摘要。

本模块不依赖 ORM，可直接导入用于单元测试。
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import secrets
from typing import TYPE_CHECKING, Protocol

from app.constants import UserRole

if TYPE_CHECKING:  # pragma: no cover - 仅供类型检查
    from app.models import User

PBKDF2_ITERATIONS = 260_000
SALT_BYTES = 16


class _HasRole(Protocol):
    role: UserRole


def hash_password(password: str, *, iterations: int = PBKDF2_ITERATIONS) -> str:
    if not password:
        raise ValueError("密码不能为空")
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations_raw, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    try:
        iterations = int(iterations_raw)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(candidate, expected)


def new_session_token() -> tuple[str, str]:
    """返回 (令牌原文, 令牌摘要)。原文只返回给客户端一次。"""

    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_expiry(now: datetime.datetime, ttl_minutes: int) -> datetime.datetime:
    return now + datetime.timedelta(minutes=ttl_minutes)


# 写操作所需的最小角色集合。查看权限对全部登录角色开放。
WRITE_ROLES: frozenset[UserRole] = frozenset({UserRole.ADMIN, UserRole.IP_ADMIN})
ADMIN_ROLES: frozenset[UserRole] = frozenset({UserRole.ADMIN})


def can_write(user: _HasRole) -> bool:
    return user.role in WRITE_ROLES


def can_admin(user: _HasRole) -> bool:
    return user.role in ADMIN_ROLES
