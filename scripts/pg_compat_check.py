"""PostgreSQL 方言兼容性检查（不需要数据库服务器）。

用 SQLAlchemy 的 PG 方言把模型 DDL 与代表性查询编译成 SQL 文本，验证：
- 22 张表能否生成合法的 PostgreSQL DDL；
- 金额/币种/JSON/枚举 CHECK 约束的列类型是否符合预期；
- 列表筛选、分页、`NULLS LAST`、统计分组等查询能否编译。

注意：这只能证明「能编译成 PG SQL」，不能替代连接真实服务器执行。

用法：
    python scripts/pg_compat_check.py
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

try:  # pragma: no cover - 环境相关
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateIndex, CreateTable
except ImportError:  # pragma: no cover
    print("跳过：未安装 SQLAlchemy。")
    raise SystemExit(0)

from app.database import Base  # noqa: E402
from app import models  # noqa: E402,F401

failures: list[str] = []


def check(condition: bool, message: str) -> None:
    if condition:
        print(f"ok   {message}")
    else:
        failures.append(message)
        print(f"FAIL {message}")


def main() -> int:
    dialect = postgresql.dialect()

    tables = Base.metadata.sorted_tables
    print(f"模型表数：{len(tables)}")

    ddl: dict[str, str] = {}
    for table in tables:
        try:
            ddl[table.name] = str(CreateTable(table).compile(dialect=dialect))
        except Exception as error:  # noqa: BLE001 - 需要报告具体编译错误
            failures.append(f"{table.name} DDL 编译失败：{error}")
            print(f"FAIL {table.name} DDL 编译失败：{error}")

    check(len(ddl) == len(tables), f"全部 {len(tables)} 张表可生成 PostgreSQL DDL")

    joined = "\n".join(ddl.values())
    check("NUMERIC(14, 2)" in joined, "金额列为 NUMERIC(14, 2)")
    check("VARCHAR(3)" in joined, "币种列为 VARCHAR(3)")
    check("JSON" in joined, "JSON 列在 PG 上为 JSON 类型")
    check("CHECK" in joined, "枚举使用 CHECK 约束而非原生枚举类型")
    check("TIMESTAMP WITH TIME ZONE" in joined, "时间列为带时区时间戳")
    check("DATE" in joined, "业务日期列为 DATE")

    # 索引能否编译
    index_failures = 0
    for table in tables:
        for index in table.indexes:
            try:
                str(CreateIndex(index).compile(dialect=dialect))
            except Exception as error:  # noqa: BLE001
                index_failures += 1
                failures.append(f"{table.name}.{index.name} 索引编译失败：{error}")
    check(index_failures == 0, "全部索引可编译")

    # 代表性查询：列表筛选 + 分页 + NULLS LAST
    from sqlalchemy import select

    from app.models import Certificate, DateItem, Fee, IpAsset

    queries = {
        "档案列表（筛选+分页）": select(IpAsset)
        .where(IpAsset.is_deleted.is_(False), IpAsset.ip_type == "patent")
        .order_by(IpAsset.updated_at.desc())
        .limit(20)
        .offset(0),
        "关键字 ILIKE 搜索": select(IpAsset).where(IpAsset.name.ilike("%示例%")),
        "证书按发证日倒序（NULLS LAST）": select(Certificate).order_by(Certificate.issue_date.desc().nulls_last()),
        "日期事项按截止日（NULLS LAST）": select(DateItem).order_by(DateItem.due_date.asc().nulls_last()),
        "费用按应付日（NULLS LAST）": select(Fee).order_by(Fee.due_date.asc().nulls_last()),
    }

    compiled: dict[str, str] = {}
    for label, statement in queries.items():
        try:
            compiled[label] = str(statement.compile(dialect=dialect))
        except Exception as error:  # noqa: BLE001
            failures.append(f"{label} 编译失败：{error}")
            print(f"FAIL {label} 编译失败：{error}")

    check(len(compiled) == len(queries), "代表性查询全部可编译")
    check(
        "NULLS LAST" in compiled.get("证书按发证日倒序（NULLS LAST）", ""),
        "NULLS LAST 正确出现在 PostgreSQL SQL 中",
    )
    check(
        "ILIKE" in compiled.get("关键字 ILIKE 搜索", ""),
        "关键字搜索编译为 ILIKE",
    )
    check(
        "LIMIT" in compiled.get("档案列表（筛选+分页）", ""),
        "分页编译为 LIMIT/OFFSET",
    )

    print()
    if failures:
        print(f"PostgreSQL 兼容性检查失败 {len(failures)} 项：")
        for item in failures:
            print(f" - {item}")
        return 1

    print("PostgreSQL 方言兼容性检查通过（DDL 与查询均可编译；未连接真实服务器）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
