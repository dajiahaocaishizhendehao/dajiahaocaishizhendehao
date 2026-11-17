"""数据一致性与 OCR 任务状态。

- 档案编号改为仅未删除记录唯一；
- 材料增加异步识别状态、结果与错误摘要。

Revision ID: 0006_integrity_ocr
Revises: 0005_invoice_code
Create Date: 2026-11-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op

revision = "0006_integrity_ocr"
down_revision = "0005_invoice_code"
branch_labels = None
depends_on = None

OCR_COLUMNS = {
    "extraction_status": sa.Column(
        "extraction_status", sa.String(length=32), nullable=False, server_default="none"
    ),
    "extraction_kind": sa.Column("extraction_kind", sa.String(length=32), nullable=True),
    "extraction_source": sa.Column("extraction_source", sa.String(length=32), nullable=True),
    "extraction_fields": sa.Column("extraction_fields", sa.JSON(), nullable=True),
    "extraction_text": sa.Column("extraction_text", sa.Text(), nullable=True),
    "extraction_error": sa.Column("extraction_error", sa.String(length=500), nullable=True),
    "extraction_started_at": sa.Column("extraction_started_at", sa.DateTime(timezone=True), nullable=True),
    "extraction_finished_at": sa.Column("extraction_finished_at", sa.DateTime(timezone=True), nullable=True),
}


def upgrade() -> None:
    if context.is_offline_mode():
        # 0001 使用当前 metadata，空库离线 DDL 已包含本迁移的最终结构。
        return
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("materials")}
    for name, column in OCR_COLUMNS.items():
        if name not in columns:
            op.add_column("materials", column)

    # 历史基线的全局唯一约束与逻辑删除冲突；SQLite 需 batch 重建表才能删除约束。
    unique_constraints = inspector.get_unique_constraints("ip_assets")
    has_global_unique = any(
        item.get("name") == "uq_ip_assets_asset_no"
        or item.get("column_names") == ["asset_no"]
        for item in unique_constraints
    )
    if has_global_unique:
        with op.batch_alter_table("ip_assets") as batch_op:
            for item in unique_constraints:
                if item.get("name") == "uq_ip_assets_asset_no":
                    batch_op.drop_constraint("uq_ip_assets_asset_no", type_="unique")

    # PostgreSQL 与 SQLite 均支持部分唯一索引。
    # 0001 以当前 metadata 建基线；0009 之后新库已没有 asset_no 列，跳过即可。
    asset_columns = {column["name"] for column in sa.inspect(bind).get_columns("ip_assets")}
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("ip_assets")}
    if "asset_no" in asset_columns and "uq_ip_assets_asset_no_active" not in indexes:
        predicate = sa.text("is_deleted = false")
        op.create_index(
            "uq_ip_assets_asset_no_active",
            "ip_assets",
            ["asset_no"],
            unique=True,
            postgresql_where=predicate,
            sqlite_where=predicate,
        )


def downgrade() -> None:
    if context.is_offline_mode():
        return
    bind = op.get_bind()
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("ip_assets")}
    if "uq_ip_assets_asset_no_active" in indexes:
        op.drop_index("uq_ip_assets_asset_no_active", table_name="ip_assets")

    with op.batch_alter_table("ip_assets") as batch_op:
        batch_op.create_unique_constraint("uq_ip_assets_asset_no", ["asset_no"])

    columns = {column["name"] for column in sa.inspect(bind).get_columns("materials")}
    for name in reversed(list(OCR_COLUMNS)):
        if name in columns:
            op.drop_column("materials", name)
