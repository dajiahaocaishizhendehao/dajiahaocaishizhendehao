"""新增台账字段：专利我方文号与年费覆盖期。

本迁移兼容两种基线：
- 历史 0001 数据库：字段不存在时补充；
- 当前空库基线：0001 已按当前 metadata 创建字段，本迁移安全跳过。

Revision ID: 0002_ledger_fields
Revises: 0001_initial
Create Date: 2026-11-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op

revision = "0002_ledger_fields"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _inspector():
    if context.is_offline_mode():
        return None
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    inspector = _inspector()
    # 离线 SQL 由当前 0001 metadata 生成完整结构，后续兼容迁移不重复输出 DDL。
    if inspector is None:
        return

    asset_columns = {column["name"] for column in inspector.get_columns("ip_assets")}
    asset_indexes = {index["name"] for index in inspector.get_indexes("ip_assets")}
    if "docket_no" not in asset_columns:
        op.add_column("ip_assets", sa.Column("docket_no", sa.String(length=64), nullable=True))
    if "ix_ip_assets_docket_no" not in asset_indexes:
        op.create_index("ix_ip_assets_docket_no", "ip_assets", ["docket_no"])

    fee_columns = {column["name"] for column in inspector.get_columns("fees")}
    fee_indexes = {index["name"] for index in inspector.get_indexes("fees")}
    if "coverage_end_date" not in fee_columns:
        op.add_column("fees", sa.Column("coverage_end_date", sa.Date(), nullable=True))
    if "ix_fees_coverage_end_date" not in fee_indexes:
        op.create_index("ix_fees_coverage_end_date", "fees", ["coverage_end_date"])


def downgrade() -> None:
    inspector = _inspector()
    if inspector is None:
        return

    asset_columns = {column["name"] for column in inspector.get_columns("ip_assets")}
    asset_indexes = {index["name"] for index in inspector.get_indexes("ip_assets")}
    fee_columns = {column["name"] for column in inspector.get_columns("fees")}
    fee_indexes = {index["name"] for index in inspector.get_indexes("fees")}

    if "ix_fees_coverage_end_date" in fee_indexes:
        op.drop_index("ix_fees_coverage_end_date", table_name="fees")
    if "coverage_end_date" in fee_columns:
        op.drop_column("fees", "coverage_end_date")
    if "ix_ip_assets_docket_no" in asset_indexes:
        op.drop_index("ix_ip_assets_docket_no", table_name="ip_assets")
    if "docket_no" in asset_columns:
        op.drop_column("ip_assets", "docket_no")
