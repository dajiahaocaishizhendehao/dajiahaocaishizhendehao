"""软著档案新增「证书获得日期」字段。

业务确认：新建软件著作权档案时需要录入证书获得日期，且与已有的「登记日期」分开保存，
因此新增 `copyrights.certificate_date`（可空 date），不复用 registration_date。

兼容历史数据库与 0001 基线（基线按当前 ORM 元数据建表）：列存在时跳过。

Revision ID: 0010_copyright_certificate_date
Revises: 0009_drop_asset_no
Create Date: 2026-11-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op

revision = "0010_copyright_certificate_date"
down_revision = "0009_drop_asset_no"
branch_labels = None
depends_on = None


def _has_certificate_date() -> bool:
    inspector = sa.inspect(op.get_bind())
    if "copyrights" not in set(inspector.get_table_names()):
        return False
    return "certificate_date" in {column["name"] for column in inspector.get_columns("copyrights")}


def upgrade() -> None:
    if context.is_offline_mode():
        return

    if _has_certificate_date():
        return

    with op.batch_alter_table("copyrights") as batch:
        batch.add_column(sa.Column("certificate_date", sa.Date(), nullable=True))


def downgrade() -> None:
    if context.is_offline_mode():
        return

    if not _has_certificate_date():
        return

    with op.batch_alter_table("copyrights") as batch:
        batch.drop_column("certificate_date")
