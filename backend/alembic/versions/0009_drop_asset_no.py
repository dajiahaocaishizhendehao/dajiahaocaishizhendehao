"""彻底删除知识产权档案的内部编号字段。

业务确认：内部编号不再由用户填写、不在页面展示，也不再保留数据库字段。
删除 `ip_assets.asset_no` 列及其唯一索引；已有编号数据不可恢复，
降级只能重建可空列，无法还原历史取值。

兼容历史数据库与当前空库基线：列/索引存在才删除。
离线模式由 0001 的当前 metadata 生成结构，本迁移不重复输出 DDL。

Revision ID: 0009_drop_asset_no
Revises: 0008_merge_user_roles
Create Date: 2026-11-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op

revision = "0009_drop_asset_no"
down_revision = "0008_merge_user_roles"
branch_labels = None
depends_on = None

ASSET_NO_INDEX = "uq_ip_assets_asset_no_active"


def _inspector():
    return sa.inspect(op.get_bind())


def _has_asset_no() -> bool:
    inspector = _inspector()
    if "ip_assets" not in set(inspector.get_table_names()):
        return False
    return "asset_no" in {column["name"] for column in inspector.get_columns("ip_assets")}


def upgrade() -> None:
    if context.is_offline_mode():
        return

    if not _has_asset_no():
        return

    index_names = {index["name"] for index in _inspector().get_indexes("ip_assets")}
    if ASSET_NO_INDEX in index_names:
        op.drop_index(ASSET_NO_INDEX, table_name="ip_assets")

    with op.batch_alter_table("ip_assets") as batch:
        batch.drop_column("asset_no")


def downgrade() -> None:
    if context.is_offline_mode():
        return

    if _has_asset_no():
        return

    with op.batch_alter_table("ip_assets") as batch:
        batch.add_column(sa.Column("asset_no", sa.String(length=64), nullable=True))

    inspector = _inspector()
    index_names = {index["name"] for index in inspector.get_indexes("ip_assets")}
    if ASSET_NO_INDEX not in index_names:
        op.create_index(
            ASSET_NO_INDEX,
            "ip_assets",
            ["asset_no"],
            unique=True,
            postgresql_where=sa.text("is_deleted = false"),
            sqlite_where=sa.text("is_deleted = false"),
        )
