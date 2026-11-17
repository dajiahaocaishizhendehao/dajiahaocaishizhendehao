"""在真实 PostgreSQL 上跑迁移与端到端验证。

用法（装好 PostgreSQL 后一条命令即可复验）：

    set DATABASE_URL=postgresql+psycopg://ipms:ipms@localhost:5432/ipms
    python scripts/pg_live_check.py

或显式传连接串：

    python scripts/pg_live_check.py --dsn postgresql+psycopg://user:pass@host:5432/db

脚本会：
1. 检查驱动是否可用并尝试连接；
2. 执行 `alembic upgrade head`；
3. 统计表数量；
4. 以该数据库启动 uvicorn 并跑完整端到端检查（32 项）。

注意：DSN 中的驱动必须与已安装的驱动一致（psycopg / psycopg2 / pg8000）。
"""

from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import sys
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"


def redact(dsn: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(dsn)
    except ValueError:
        return "<无法解析的 DSN>"
    if parsed.password:
        netloc = f"{parsed.username}:***@{parsed.hostname}"
        if parsed.port:
            netloc += f":{parsed.port}"
        return urllib.parse.urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
    return dsn


def main() -> int:
    parser = argparse.ArgumentParser(description="在真实 PostgreSQL 上验证")
    parser.add_argument("--dsn", default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument("--skip-migrate", action="store_true", help="跳过 alembic upgrade")
    args = parser.parse_args()

    dsn = args.dsn.strip()
    if not dsn or dsn.startswith("sqlite"):
        print("请提供 PostgreSQL 连接串，例如：")
        print("  python scripts/pg_live_check.py --dsn postgresql+psycopg://user:pass@localhost:5432/ipms")
        return 2

    print(f"目标数据库：{redact(dsn)}")
    env = dict(os.environ)
    env["DATABASE_URL"] = dsn
    env["PYTHONPATH"] = os.pathsep.join([str(BACKEND), os.environ.get("PYTHONPATH", "")]).strip(os.pathsep)

    # 1. 连接探测
    probe_code = (
        "import sys;"
        "from sqlalchemy import create_engine, text;"
        "engine = create_engine(sys.argv[1]);"
        "conn = engine.connect();"
        "print('server_version=' + conn.execute(text('show server_version')).scalar());"
        "conn.close(); engine.dispose()"
    )
    probe = subprocess.run([sys.executable, "-c", probe_code, dsn], capture_output=True, text=True, env=env)
    if probe.returncode != 0:
        print("连接失败：")
        print((probe.stderr or probe.stdout).strip()[-800:])
        print("\n常见原因：数据库未启动、账号密码错误、驱动未安装（psycopg / psycopg2）。")
        return 1
    print(f"连接成功：{probe.stdout.strip()}")

    # 2. 迁移
    if not args.skip_migrate:
        migration = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=str(BACKEND),
            capture_output=True,
            text=True,
            env=env,
        )
        if migration.returncode != 0:
            print("迁移失败：")
            print((migration.stderr or migration.stdout).strip()[-1500:])
            return 1
        print("迁移完成：alembic upgrade head")

    # 3. 表数量
    count_code = (
        "import sys;"
        "from sqlalchemy import create_engine, inspect;"
        "engine = create_engine(sys.argv[1]);"
        "tables = inspect(engine).get_table_names();"
        "print(f'tables={len(tables)}');"
        "print(', '.join(sorted(tables)));"
        "engine.dispose()"
    )
    counting = subprocess.run([sys.executable, "-c", count_code, dsn], capture_output=True, text=True, env=env)
    print(counting.stdout.strip() or counting.stderr.strip()[-800:])

    # 4. 端到端
    live_env = dict(env)
    live_env["IPMS_LIVE_DSN"] = dsn
    live = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "live_api_check.py")],
        capture_output=True,
        text=True,
        env=live_env,
    )
    tail = (live.stdout or "").strip().splitlines()
    for line in tail[-40:]:
        print(line)
    if live.returncode != 0:
        print("\n端到端验证失败：")
        print((live.stderr or "").strip()[-1200:])
        return 1

    print("\nPostgreSQL 实连验证通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
