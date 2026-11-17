"""请求上下文工具（不依赖数据库与 ORM）。

放在独立模块的原因：审计日志会调用它记录来源 IP，而该逻辑应当可以在
没有 SQLAlchemy 的环境里单独测试。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - 仅供类型检查
    from starlette.requests import Request


def client_ip(request: "Request | None") -> str | None:
    """取请求来源 IP：优先 X-Forwarded-For 第一段，其次连接地址。"""

    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.client.host if request.client else None
