"""角色精简为系统管理员、管理员、普通用户。

业务确认：角色只保留 `admin`（系统管理员）、`ip_admin`（管理员）、
`user`（普通用户）。原 `dept_user` 与 `viewer` 都是只读角色，合并为 `user`；
写权限规则不变。

角色以 VARCHAR 存储（`native_enum=False`），数据库没有原生枚举类型，
因此本迁移只需转换已有账号的取值。

Revision ID: 0008_merge_user_roles
Revises: 0007_drop_departments
Create Date: 2026-11-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op

revision = "0008_merge_user_roles"
down_revision = "0007_drop_departments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if context.is_offline_mode():
        return

    inspector = sa.inspect(op.get_bind())
    if "users" not in set(inspector.get_table_names()):
        return

    op.execute(
        sa.text("UPDATE users SET role = 'user' WHERE role IN ('dept_user', 'viewer')")
    )


def downgrade() -> None:
    if context.is_offline_mode():
        return

    inspector = sa.inspect(op.get_bind())
    if "users" not in set(inspector.get_table_names()):
        return

    # 合并不可精确还原：原 dept_user 与 viewer 都回退为只读的 viewer。
    op.execute(sa.text("UPDATE users SET role = 'viewer' WHERE role = 'user'"))
