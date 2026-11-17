"""删除纸质原件台账相关表。

兼容历史数据库与当前空库基线：表存在才删除；当前 0001 基线不再创建这两张表。

Revision ID: 0003_drop_originals
Revises: 0002_ledger_fields
Create Date: 2026-11-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op

revision = "0003_drop_originals"
down_revision = "0002_ledger_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if context.is_offline_mode():
        return
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "original_loans" in tables:
        op.drop_table("original_loans")
    if "originals" in tables:
        op.drop_table("originals")


def downgrade() -> None:
    if context.is_offline_mode():
        return
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "originals" not in tables:
        op.create_table(
            "originals",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("ip_asset_id", sa.String(length=36), sa.ForeignKey("ip_assets.id")),
            sa.Column("certificate_id", sa.String(length=36), sa.ForeignKey("certificates.id")),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("item_type", sa.String(length=64), nullable=False),
            sa.Column("copies", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("location", sa.String(length=128)),
            sa.Column("keeper", sa.String(length=64)),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="in_storage"),
            sa.Column("received_date", sa.Date()),
            sa.Column("remark", sa.Text()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("created_by", sa.String(length=36)),
            sa.Column("updated_by", sa.String(length=36)),
            sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "original_loans" not in tables:
        op.create_table(
            "original_loans",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("original_id", sa.String(length=36), sa.ForeignKey("originals.id"), nullable=False),
            sa.Column("borrower", sa.String(length=64), nullable=False),
            sa.Column("loan_date", sa.Date(), nullable=False),
            sa.Column("due_date", sa.Date()),
            sa.Column("return_date", sa.Date()),
            sa.Column("purpose", sa.Text()),
            sa.Column("handled_by", sa.String(length=36), sa.ForeignKey("users.id")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
