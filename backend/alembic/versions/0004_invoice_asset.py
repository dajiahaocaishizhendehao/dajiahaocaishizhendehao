"""发票归属案件：发票需要能按案件检索。

兼容历史数据库与当前空库基线：列、索引、外键不存在时才补充。
当前 0001 metadata 已包含它们，空库迁移会安全跳过。

Revision ID: 0004_invoice_asset
Revises: 0003_drop_originals
Create Date: 2026-11-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op

revision = "0004_invoice_asset"
down_revision = "0003_drop_originals"
branch_labels = None
depends_on = None

COLUMN = "ip_asset_id"
INDEX = "ix_invoices_ip_asset_id"
FK = "fk_invoices_ip_asset"


def _inspector():
    if context.is_offline_mode():
        return None
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    inspector = _inspector()
    if inspector is None:
        return

    columns = {column["name"] for column in inspector.get_columns("invoices")}
    indexes = {index["name"] for index in inspector.get_indexes("invoices")}
    foreign_keys = inspector.get_foreign_keys("invoices")

    if COLUMN not in columns:
        op.add_column("invoices", sa.Column(COLUMN, sa.String(length=36), nullable=True))
    if INDEX not in indexes:
        op.create_index(INDEX, "invoices", [COLUMN])

    has_asset_fk = any(
        fk.get("referred_table") == "ip_assets" and fk.get("constrained_columns") == [COLUMN]
        for fk in foreign_keys
    )
    if op.get_bind().dialect.name != "sqlite" and not has_asset_fk:
        op.create_foreign_key(FK, "invoices", "ip_assets", [COLUMN], ["id"])


def downgrade() -> None:
    inspector = _inspector()
    if inspector is None:
        return

    columns = {column["name"] for column in inspector.get_columns("invoices")}
    indexes = {index["name"] for index in inspector.get_indexes("invoices")}
    foreign_keys = inspector.get_foreign_keys("invoices")
    asset_fk = next(
        (
            fk
            for fk in foreign_keys
            if fk.get("referred_table") == "ip_assets" and fk.get("constrained_columns") == [COLUMN]
        ),
        None,
    )
    if op.get_bind().dialect.name != "sqlite" and asset_fk and asset_fk.get("name"):
        op.drop_constraint(asset_fk["name"], "invoices", type_="foreignkey")
    if INDEX in indexes:
        op.drop_index(INDEX, table_name="invoices")
    if COLUMN in columns:
        op.drop_column("invoices", COLUMN)
