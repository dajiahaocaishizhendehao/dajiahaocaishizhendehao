"""数据库会话与基类。

引擎按需创建（懒加载），这样只使用 Base.metadata 的工具（例如方言兼容性检查、
模型静态检查）不需要安装数据库驱动，也不会在导入时建立连接池。
"""

from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

SessionLocal = sessionmaker(autoflush=False, expire_on_commit=False, class_=Session)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(settings.database_url, pool_pre_ping=True, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal(bind=get_engine())
    try:
        yield db
    finally:
        db.close()
