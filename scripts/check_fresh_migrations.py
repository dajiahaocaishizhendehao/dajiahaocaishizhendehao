"""验证 Alembic 迁移链可在全新 SQLite 数据库执行到 head。

    python scripts/check_fresh_migrations.py
"""

from __future__ import annotations

import os
import pathlib
import sqlite3
import subprocess
import sys
import uuid

ROOT = pathlib.Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
VAR = BACKEND / "var"


def main() -> int:
    VAR.mkdir(parents=True, exist_ok=True)
    database = VAR / f"migration-check-{uuid.uuid4().hex}.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+pysqlite:///{database.as_posix()}"
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
        )
        if completed.returncode != 0:
            print(completed.stdout)
            print(completed.stderr, file=sys.stderr)
            return completed.returncode

        connection = sqlite3.connect(database)
        try:
            tables = {
                row[0]
                for row in connection.execute(
                    "select name from sqlite_master where type='table' and name not like 'sqlite_%'"
                )
            }
            version = connection.execute("select version_num from alembic_version").fetchone()[0]
            invoice_columns = {row[1] for row in connection.execute("pragma table_info(invoices)")}
            asset_columns = {row[1] for row in connection.execute("pragma table_info(ip_assets)")}
            fee_columns = {row[1] for row in connection.execute("pragma table_info(fees)")}
            material_columns = {row[1] for row in connection.execute("pragma table_info(materials)")}
        finally:
            connection.close()

        assertions = {
            "head 版本": version == "0006_integrity_ocr",
            "业务表数量": len(tables - {"alembic_version"}) == 20,
            "原件表已删除": "originals" not in tables and "original_loans" not in tables,
            "我方文号字段": "docket_no" in asset_columns,
            "年费覆盖字段": "coverage_end_date" in fee_columns,
            "发票案件字段": "ip_asset_id" in invoice_columns,
            "发票代码字段": "invoice_code" in invoice_columns,
            "OCR 状态字段": "extraction_status" in material_columns,
        }
        for label, ok in assertions.items():
            print(("ok  " if ok else "FAIL"), label)
        return 0 if all(assertions.values()) else 1
    finally:
        database.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
