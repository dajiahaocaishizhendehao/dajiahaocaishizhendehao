"""创建初始管理员账号。

用法：
    python -m tools.create_admin --username admin --password 'ChangeMe!123' --name 管理员
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from app import security
from app.database import SessionLocal, get_engine
from app.models import User, UserRole


def main() -> int:
    parser = argparse.ArgumentParser(description="创建知识产权管理系统管理员")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--name", default="管理员")
    args = parser.parse_args()

    if len(args.password) < 8:
        print("密码至少 8 位", file=sys.stderr)
        return 2

    with SessionLocal(bind=get_engine()) as db:
        existing = db.scalar(select(User).where(User.username == args.username))
        if existing is not None:
            print(f"用户已存在: {args.username}", file=sys.stderr)
            return 1
        user = User(
            username=args.username,
            display_name=args.name,
            password_hash=security.hash_password(args.password),
            role=UserRole.ADMIN,
        )
        db.add(user)
        db.commit()
        print(f"已创建管理员: {args.username}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
