"""服务层公共逻辑：审计、分页、数据范围与编号校验。"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request, status
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models import AuditLog, Fee, IpAsset, Material, User
from app.query import clamp_pagination
from app.request_context import client_ip


def write_audit(
    db: Session,
    *,
    user: User | None,
    action: str,
    object_type: str,
    object_id: str | None = None,
    summary: str | None = None,
    detail: dict[str, Any] | None = None,
    request: Request | None = None,
) -> None:
    """记录关键操作。禁止写入密码、令牌或文件内容。"""

    db.add(
        AuditLog(
            user_id=user.id if user else None,
            action=action,
            object_type=object_type,
            object_id=object_id,
            summary=summary,
            detail=detail,
            ip_address=client_ip(request),
        )
    )


def paginate(db: Session, stmt: Select, *, page: int, page_size: int) -> tuple[list[Any], int]:
    page, page_size = clamp_pagination(page, page_size)
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = db.scalars(stmt.limit(page_size).offset((page - 1) * page_size)).all()
    return list(rows), int(total)


def scoped_assets(stmt: Select, user: User) -> Select:
    """所有登录用户可见全部未删除档案；保留函数名以统一调用入口。"""

    return stmt


def ensure_asset_visible(asset: IpAsset | None, user: User) -> IpAsset:
    if asset is None or asset.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="档案不存在")
    return asset


def scoped_asset_ids(user: User) -> Select:
    """当前可见（未删除）的档案 ID 子查询。

    供费用、发票、材料、日期、证书等关联资源统一复用。
    """

    return select(IpAsset.id).where(IpAsset.is_deleted.is_(False))


def scoped_related(
    stmt: Select,
    asset_column,
    user: User,
    *,
    include_unassigned_for_admin: bool = True,
    include_deleted_parent: bool = False,
) -> Select:
    """为带 ``ip_asset_id`` 的业务表追加统一的父档案过滤。"""

    return stmt.where(
        related_scope_condition(asset_column, user, include_deleted_parent=include_deleted_parent)
    )


def related_scope_condition(asset_column, user: User, *, include_deleted_parent: bool = False):
    """允许未关联记录；关联记录必须指向存在（且未删除）的档案。"""

    if include_deleted_parent:
        return or_(asset_column.is_(None), asset_column.in_(select(IpAsset.id)))
    return or_(asset_column.is_(None), asset_column.in_(scoped_asset_ids(user)))


def ensure_related_visible(db: Session, asset_id: str | None, user: User, *, detail: str) -> IpAsset | None:
    """校验单条关联资源指向的档案存在且未删除。"""

    if asset_id is None:
        return None
    try:
        return ensure_asset_visible(db.get(IpAsset, asset_id), user)
    except HTTPException:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail) from None


def ensure_material_reference(
    db: Session,
    material_id: str | None,
    asset_id: str | None,
    user: User,
    *,
    field_label: str = "附件",
) -> Material | None:
    if material_id is None:
        return None
    material = db.get(Material, material_id)
    if material is None or material.is_deleted:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{field_label}不存在")
    ensure_related_visible(db, material.ip_asset_id, user, detail=f"{field_label}不存在")
    if material.ip_asset_id != asset_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_label}必须属于同一案件",
        )
    return material


def ensure_invoice_fees(
    db: Session,
    fee_ids: list[str],
    asset_id: str | None,
    user: User,
) -> list[Fee]:
    fees: list[Fee] = []
    for fee_id in dict.fromkeys(fee_ids):
        fee = db.get(Fee, fee_id)
        if fee is None or fee.is_deleted:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"费用不存在: {fee_id}")
        ensure_related_visible(db, fee.ip_asset_id, user, detail=f"费用不存在: {fee_id}")
        if fee.ip_asset_id != asset_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="发票与费用必须属于同一案件")
        fees.append(fee)
    return fees


def ensure_type_payload(ip_type, patent, copyright_, trademark) -> None:
    """同一档案只能提交与类型匹配的专业字段；规则定义在 domain 模块。"""

    from app.domain import DomainError, validate_type_payload

    try:
        validate_type_payload(ip_type, patent, copyright_, trademark)
    except DomainError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from None
