"""发票代码字段。

兼容历史数据库与当前空库基线：字段不存在时才补充。

Revision ID: 0005_invoice_code
Revises: 0004_invoice_asset
Create Date: 2026-11-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op

revision = "0005_invoice_code"
down_revision = "0004_invoice_asset"
branch_labels = None
depends_on = None

COLUMN = "invoice_code"


def _inspector():
    if context.is_offline_mode():
        return None
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    inspector = _inspector()
    if inspector is None:
        return
    columns = {column["name"] for column in inspector.get_columns("invoices")}
    if COLUMN not in columns:
        op.add_column("invoices", sa.Column(COLUMN, sa.String(length=32), nullable=True))


def downgrade() -> None:
    inspector = _inspector()
    if inspector is None:
        return
    columns = {column["name"] for column in inspector.get_columns("invoices")}
    if COLUMN in columns:
        op.drop_column("invoices", COLUMN)
