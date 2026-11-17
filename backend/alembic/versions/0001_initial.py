"""基线迁移：按 ORM 元数据创建全部业务表。

说明（TODO(CONFIRM)）：本迁移以 ORM 元数据为准建立基线，保证与模型零漂移。
后续任何结构调整都必须使用显式 op.create_table / op.add_column 的增量迁移，
不得再修改本文件。
"""

from __future__ import annotations

from alembic import op

from app.database import Base
from app import models  # noqa: F401  注册全部模型

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
