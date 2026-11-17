"""校验 Alembic 在 PostgreSQL 方言下生成的建表 SQL（离线，无需服务器）。

做法：用 `alembic upgrade head --sql` 的离线模式，让 Alembic 以 PostgreSQL 方言
渲染出实际会执行的 DDL，然后对它做结构性断言。

这比「直接编译 metadata」更接近真实迁移路径，因为它走的是 alembic env + 迁移脚本。

用法：
    python scripts/pg_ddl_check.py
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
OUTPUT = BACKEND / "var" / "schema-postgres.sql"

# 不需要真实连接：离线模式只渲染 SQL。
DSN = "postgresql+psycopg2://ipms:ipms@127.0.0.1:5432/ipms"

EXPECTED_TABLES = 19

failures: list[str] = []


def check(condition: bool, message: str) -> None:
    if condition:
        print(f"ok   {message}")
    else:
        failures.append(message)
        print(f"FAIL {message}")


def main() -> int:
    env = dict(os.environ)
    env["DATABASE_URL"] = DSN
    env["PYTHONPATH"] = os.pathsep.join([str(BACKEND), os.environ.get("PYTHONPATH", "")]).strip(os.pathsep)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=str(BACKEND),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    if result.returncode != 0:
        print("生成 SQL 失败：")
        print((result.stderr or result.stdout).strip()[-1500:])
        return 1

    sql = result.stdout
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(sql, encoding="utf-8")

    creates = re.findall(r"CREATE TABLE (\w+)", sql)
    business_tables = [name for name in creates if name != "alembic_version"]

    print(f"已生成 {OUTPUT.relative_to(ROOT)}（{len(sql.splitlines())} 行）\n")
    check(len(business_tables) == EXPECTED_TABLES, f"业务表数量为 {len(business_tables)}（期望 {EXPECTED_TABLES}）")

    joined = sql.upper()
    check("NUMERIC(14, 2)" in sql, "金额列为 NUMERIC(14, 2)")
    check("VARCHAR(3)" in sql, "币种列为 VARCHAR(3)")
    check("JSON" in joined, "JSON 列在 PG 上为 JSON")
    check("TIMESTAMP WITH TIME ZONE" in joined, "时间列为带时区时间戳")
    check("DATE" in joined, "存在业务日期列")
    check("CHECK" in joined, "枚举使用 CHECK 约束")
    check("PRIMARY KEY" in joined, "包含主键约束")
    check(len(re.findall(r"FOREIGN KEY", joined)) >= 15, "外键约束数量合理")
    check("CREATE INDEX" in joined or "CREATE UNIQUE INDEX" in joined, "包含索引定义")
    check("alembic_version" in sql, "包含版本表")

    # 关键唯一约束
    check("uq_invoice_fee" in sql, "发票-费用关联唯一约束存在")
    # 迁移注释里会出现 revision 名称，所以只检查非注释 SQL。
    executable_sql = "\n".join(
        line for line in sql.splitlines() if not line.lstrip().startswith("--")
    )
    check(
        "uq_ip_assets_asset_no_active" not in executable_sql
        and re.search(r"\basset_no\s+(VARCHAR|TEXT|CHAR)", executable_sql) is None,
        "内部编号列与唯一索引已彻底移除",
    )

    # 确认没有 SQLite 专有语法泄漏
    check("AUTOINCREMENT" not in joined, "不含 SQLite 专有语法 AUTOINCREMENT")

    print()
    if failures:
        print(f"PostgreSQL DDL 检查失败 {len(failures)} 项：")
        for item in failures:
            print(f" - {item}")
        return 1

    print("PostgreSQL DDL 检查通过（由 Alembic 离线模式生成，未连接服务器）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
