"""取消部门字段与部门表。

业务确认：不再保留部门，也不再用部门限制数据可见范围。
所有登录用户均可查看全部未删除档案；写权限仍由角色控制。

兼容历史数据库与当前空库基线：字段/表存在才删除。
离线模式由 0001 的当前 metadata 生成结构，本迁移不重复输出 DDL。

Revision ID: 0007_drop_departments
Revises: 0006_integrity_ocr
Create Date: 2026-11-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op

revision = "0007_drop_departments"
down_revision = "0006_integrity_ocr"
branch_labels = None
depends_on = None

# 需要移除 department_id 的业务表。
TABLES_WITH_DEPARTMENT = ("users", "projects", "persons", "ip_assets")


def _inspector():
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    if context.is_offline_mode():
        return

    inspector = _inspector()
    table_names = set(inspector.get_table_names())
    for table_name in TABLES_WITH_DEPARTMENT:
        if table_name not in table_names:
            continue
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        if "department_id" not in columns:
            continue
        with op.batch_alter_table(table_name) as batch:
            batch.drop_column("department_id")

    table_names = set(_inspector().get_table_names())
    if "departments" in table_names:
        op.drop_table("departments")


def downgrade() -> None:
    if context.is_offline_mode():
        return

    inspector = _inspector()
    table_names = set(inspector.get_table_names())
    if "departments" not in table_names:
        op.create_table(
            "departments",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("code", sa.String(length=64), unique=True),
            sa.Column("parent_id", sa.String(length=36), sa.ForeignKey("departments.id")),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("created_by", sa.String(length=36)),
            sa.Column("updated_by", sa.String(length=36)),
            sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        )

    inspector = _inspector()
    table_names = set(inspector.get_table_names())
    for table_name in TABLES_WITH_DEPARTMENT:
        if table_name not in table_names:
            continue
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        if "department_id" in columns:
            continue
        with op.batch_alter_table(table_name) as batch:
            batch.add_column(
                sa.Column("department_id", sa.String(length=36), sa.ForeignKey("departments.id"))
            )
