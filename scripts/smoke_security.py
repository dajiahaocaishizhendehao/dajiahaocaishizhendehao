"""安全模块自检（不依赖第三方库，可直接运行）。

用法：
    python scripts/smoke_security.py

覆盖：密码哈希可验证、盐随机、篡改不可通过、令牌摘要、会话过期、角色与数据范围。
"""

from __future__ import annotations

import datetime
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))

from app import security  # noqa: E402
from app.constants import UserRole  # noqa: E402


class FakeUser:
    def __init__(self, role: UserRole) -> None:
        self.role = role


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"ok - {message}")


def main() -> int:
    stored = security.hash_password("Passw0rd!")
    check(stored.startswith("pbkdf2_sha256$"), "哈希包含算法标识")
    check("Passw0rd!" not in stored, "哈希不包含明文密码")
    check(security.verify_password("Passw0rd!", stored), "正确密码通过验证")
    check(not security.verify_password("passw0rd!", stored), "大小写不同被拒绝")
    check(not security.verify_password("Passw0rd!", stored[:-2] + "00"), "篡改摘要被拒绝")

    second = security.hash_password("Passw0rd!")
    check(stored != second, "相同密码两次哈希不同（随机盐）")

    check(not security.verify_password("x", "not-a-hash"), "非法哈希格式被拒绝")
    check(not security.verify_password("x", "md5$1$aa$bb"), "未知算法被拒绝")

    token, digest = security.new_session_token()
    check(len(token) >= 32, "令牌长度足够")
    check(digest == security.hash_token(token), "摘要与令牌一致")
    check(token != digest, "摘要与原文不同")

    now = datetime.datetime(2026, 11, 5, tzinfo=datetime.timezone.utc)
    check(
        security.session_expiry(now, 60) == now + datetime.timedelta(minutes=60),
        "会话过期时间按分钟计算",
    )

    admin = FakeUser(UserRole.ADMIN)
    ip_admin = FakeUser(UserRole.IP_ADMIN)
    user = FakeUser(UserRole.USER)

    check(security.can_write(admin) and security.can_write(ip_admin), "管理员可写")
    check(not security.can_write(user), "普通用户不可写")
    check(security.can_admin(admin) and not security.can_admin(ip_admin), "仅系统管理员可管用户")

    print("\n安全自检全部通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
