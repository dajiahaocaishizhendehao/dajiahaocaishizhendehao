"""日期事项与提醒。

系统只保存用户录入的日期与提醒规则，不推导法律期限。
"""

from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_write, utcnow
from app.models import DateItem, DateStatus, DateType, IpAsset, User
from app.schemas import DateItemIn, DateItemOut, DateItemUpdate, Page
from app.services import ensure_asset_visible, ensure_related_visible, paginate, scoped_related, write_audit

router = APIRouter(prefix="/dates", tags=["日期与提醒"])


@router.get("", response_model=Page[DateItemOut])
def list_dates(
    q: str | None = Query(default=None, max_length=128),
    ip_asset_id: str | None = None,
    date_type: DateType | None = None,
    status_filter: DateStatus | None = Query(default=None, alias="status"),
    due_from: datetime.date | None = None,
    due_to: datetime.date | None = None,
    include_deleted_parent: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Page[DateItemOut]:
    stmt = scoped_related(
        select(DateItem).where(DateItem.is_deleted.is_(False)),
        DateItem.ip_asset_id,
        user,
        include_deleted_parent=include_deleted_parent,
    )
    if q:
        stmt = stmt.where(or_(DateItem.title.ilike(f"%{q}%"), DateItem.remark.ilike(f"%{q}%")))
    if ip_asset_id:
        ensure_asset_visible(db.get(IpAsset, ip_asset_id), user)
        stmt = stmt.where(DateItem.ip_asset_id == ip_asset_id)
    if date_type:
        stmt = stmt.where(DateItem.date_type == date_type)
    if status_filter:
        stmt = stmt.where(DateItem.status == status_filter)
    if due_from:
        stmt = stmt.where(DateItem.due_date >= due_from)
    if due_to:
        stmt = stmt.where(DateItem.due_date <= due_to)

    rows, total = paginate(db, stmt.order_by(DateItem.due_date.asc().nulls_last()), page=page, page_size=page_size)
    asset_ids = {row.ip_asset_id for row in rows if row.ip_asset_id}
    asset_names: dict[str, str] = {}
    if asset_ids:
        asset_names = {
            asset.id: asset.name for asset in db.scalars(select(IpAsset).where(IpAsset.id.in_(asset_ids)))
        }
    items = [
        DateItemOut.model_validate(row).model_copy(update={"asset_name": asset_names.get(row.ip_asset_id)})
        for row in rows
    ]
    return Page[DateItemOut](items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=DateItemOut, status_code=status.HTTP_201_CREATED)
def create_date(
    payload: DateItemIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_write),
) -> DateItemOut:
    if payload.ip_asset_id:
        ensure_asset_visible(db.get(IpAsset, payload.ip_asset_id), user)
    item = DateItem(**payload.model_dump(), created_by=user.id, updated_by=user.id)
    db.add(item)
    db.flush()
    write_audit(
        db,
        user=user,
        action="create",
        object_type="date_item",
        object_id=item.id,
        summary=item.title,
        request=request,
    )
    db.commit()
    return DateItemOut.model_validate(item)


@router.patch("/{item_id}", response_model=DateItemOut)
def update_date(
    item_id: str,
    payload: DateItemUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_write),
) -> DateItemOut:
    item = db.get(DateItem, item_id)
    if item is None or item.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="日期事项不存在")
    ensure_related_visible(db, item.ip_asset_id, user, detail="日期事项不存在")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    item.updated_by = user.id
    write_audit(
        db,
        user=user,
        action="update",
        object_type="date_item",
        object_id=item.id,
        summary=item.title,
        request=request,
    )
    db.commit()
    return DateItemOut.model_validate(item)


@router.post("/{item_id}/complete", response_model=DateItemOut)
def complete_date(
    item_id: str,
    request: Request,
    actual_date: datetime.date | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_write),
) -> DateItemOut:
    item = db.get(DateItem, item_id)
    if item is None or item.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="日期事项不存在")
    ensure_related_visible(db, item.ip_asset_id, user, detail="日期事项不存在")

    item.status = DateStatus.DONE
    item.actual_date = actual_date or utcnow().date()
    item.updated_by = user.id
    # 完成后不再触发提醒，但保留历史记录。
    item.remind_at = None
    write_audit(
        db,
        user=user,
        action="complete",
        object_type="date_item",
        object_id=item.id,
        summary=item.title,
        request=request,
    )
    db.commit()
    return DateItemOut.model_validate(item)
