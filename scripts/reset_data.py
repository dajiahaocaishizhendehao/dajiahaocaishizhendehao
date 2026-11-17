"""清空本地业务数据，用于重新测试。

默认保留登录账号（admin），只清空业务表、审计日志、会话与已上传文件。
执行前会自动备份数据库到 backend/var/backup-<时间戳>.db。

用法：
    python scripts/reset_data.py                # 备份 + 清空，保留 admin
    python scripts/reset_data.py --dry-run      # 只显示将删除的数量
    python scripts/reset_data.py --drop-users   # 连用户一起清空（会无法登录）
"""

from __future__ import annotations

import argparse
import datetime
import pathlib
import shutil
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
VAR = ROOT / "backend" / "var"
DB = VAR / "ipms.db"
STORAGE = VAR / "storage"

# 按依赖顺序删除；保留 alembic_version。
BUSINESS_TABLES = [
    "invoice_fees",
    "invoices",
    "fees",
    "materials",
    "date_items",
    "certificates",
    "trademarks",
    "copyrights",
    "patents",
    "asset_parties",
    "asset_persons",
    "ip_assets",
    "parties",
    "persons",
    "agencies",
    "projects",
    "audit_logs",
    "auth_sessions",
]
KEEP_USERS = {"admin"}


def main() -> int:
    parser = argparse.ArgumentParser(description="清空本地业务数据")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--drop-users", action="store_true")
    args = parser.parse_args()

    if not DB.exists():
        print(f"数据库不存在：{DB}")
        return 1

    connection = sqlite3.connect(DB)
    try:
        if args.dry_run:
            for table in BUSINESS_TABLES:
                count = connection.execute(f'select count(*) from "{table}"').fetchone()[0]
                print(f"{table:24} {count}")
            users = connection.execute("select username from users").fetchall()
            print("users:", [row[0] for row in users])
            return 0

        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = VAR / f"backup-{stamp}.db"
        connection.close()
        shutil.copy2(DB, backup)
        print(f"已备份数据库：{backup}")

        connection = sqlite3.connect(DB)
        connection.execute("PRAGMA foreign_keys = OFF")
        for table in BUSINESS_TABLES:
            connection.execute(f'delete from "{table}"')
            print(f"已清空 {table}")

        if args.drop_users:
            connection.execute("delete from users")
            print("已清空 users（需要重新初始化管理员）")
        else:
            names = [row[0] for row in connection.execute("select username from users").fetchall()]
            for name in names:
                if name not in KEEP_USERS:
                    connection.execute("delete from users where username = ?", (name,))
            kept = [row[0] for row in connection.execute("select username from users").fetchall()]
            print("保留用户:", kept)

        connection.commit()
    finally:
        connection.close()

    removed = 0
    if STORAGE.exists():
        for path in STORAGE.iterdir():
            if path.is_file():
                path.unlink(missing_ok=True)
                removed += 1
    print(f"已删除存储文件 {removed} 个")

    verify = sqlite3.connect(DB)
    try:
        for table in ("ip_assets", "fees", "materials", "date_items", "users"):
            count = verify.execute(f'select count(*) from "{table}"').fetchone()[0]
            print(f"{table:12} 剩余 {count}")
    finally:
        verify.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
