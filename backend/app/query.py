"""查询条件与分页参数（纯逻辑，不依赖 ORM）。

把查询条件的规范化从 SQL 拼接中剥离出来，便于独立验证。
所有登录用户的数据可见范围一致；写权限仍由 deps 中的角色校验控制。
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 200


@dataclass(frozen=True)
class AssetQuery:
    """档案列表的查询条件（规范化后）。"""

    q: str | None = None
    ip_type: str | None = None
    status_group: str | None = None
    project_id: str | None = None
    owner_user_id: str | None = None


def _clean(value: str | None) -> str | None:
    """去空格，空串按未填写处理，避免出现 LIKE '%%' 之类的无意义条件。"""

    if value is None:
        return None
    text = value.strip()
    return text or None


def normalize_asset_query(
    *,
    q: str | None = None,
    ip_type: str | None = None,
    status_group: str | None = None,
    project_id: str | None = None,
    owner_user_id: str | None = None,
) -> AssetQuery:
    return AssetQuery(
        q=_clean(q),
        ip_type=_clean(ip_type),
        status_group=_clean(status_group),
        project_id=_clean(project_id),
        owner_user_id=_clean(owner_user_id),
    )


def clamp_pagination(page: int | None, page_size: int | None) -> tuple[int, int]:
    """把分页参数收敛到安全区间，避免超大 page_size 拖垮数据库。"""

    safe_page = page if isinstance(page, int) and page >= 1 else 1
    safe_size = page_size if isinstance(page_size, int) and page_size >= 1 else DEFAULT_PAGE_SIZE
    return safe_page, min(safe_size, MAX_PAGE_SIZE)
