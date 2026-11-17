"""知识产权主档接口：统一列表、详情、创建、修改与逻辑删除。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import case, delete, or_, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import get_current_user, require_write
from app.models import (
    AssetParty,
    AssetPerson,
    AssetStatus,
    Copyright,
    IpAsset,
    IpType,
    Patent,
    Party,
    Person,
    Trademark,
    User,
)
from app.schemas import (
    AssetCreate,
    AssetDetail,
    AssetListItem,
    AssetPartyIn,
    AssetUpdate,
    Page,
    PartyOut,
    PersonOut,
)
from app.services import (
    ensure_asset_visible,
    ensure_type_payload,
    paginate,
    write_audit,
)
from app.query import normalize_asset_query

router = APIRouter(prefix="/assets", tags=["知识产权档案"])


def _load_asset(db: Session, asset_id: str) -> IpAsset | None:
    return db.scalar(
        select(IpAsset)
        .options(selectinload(IpAsset.patent), selectinload(IpAsset.copyright), selectinload(IpAsset.trademark))
        .where(IpAsset.id == asset_id)
    )


def _asset_detail(db: Session, asset: IpAsset) -> AssetDetail:
    detail = AssetDetail.model_validate(asset)
    party_rows = db.execute(
        select(AssetParty, Party)
        .join(Party, Party.id == AssetParty.party_id)
        .where(AssetParty.ip_asset_id == asset.id)
        .order_by(AssetParty.seq)
    ).all()
    person_rows = db.execute(
        select(AssetPerson, Person)
        .join(Person, Person.id == AssetPerson.person_id)
        .where(AssetPerson.ip_asset_id == asset.id)
        .order_by(AssetPerson.seq)
    ).all()
    detail.parties = [PartyOut.model_validate(party) for _, party in party_rows]
    detail.persons = [PersonOut.model_validate(person) for _, person in person_rows]
    return detail


@router.get("", response_model=Page[AssetListItem])
def list_assets(
    q: str | None = Query(default=None, max_length=128),
    ip_type: IpType | None = None,
    status_group: AssetStatus | None = None,
    project_id: str | None = None,
    owner_user_id: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Page[AssetListItem]:
    query = normalize_asset_query(
        q=q,
        ip_type=ip_type.value if ip_type else None,
        status_group=status_group.value if status_group else None,
        project_id=project_id,
        owner_user_id=owner_user_id,
    )

    # 排序口径：未取得权利的最前；已取得的按授权公告日倒序
    # （专利取 patents.grant_date，软著取 copyrights.certificate_date）；
    # 已取得但无授权公告日的排在最后，同组按更新时间倒序。
    grant_date = case(
        (IpAsset.ip_type == IpType.PATENT, Patent.grant_date),
        (IpAsset.ip_type == IpType.COPYRIGHT, Copyright.certificate_date),
    )
    sort_group = case(
        (IpAsset.status_group != AssetStatus.GRANTED, 0),
        (grant_date.is_(None), 2),
        else_=1,
    )

    stmt = (
        select(IpAsset)
        .outerjoin(Patent, Patent.ip_asset_id == IpAsset.id)
        .outerjoin(Copyright, Copyright.ip_asset_id == IpAsset.id)
        .where(IpAsset.is_deleted.is_(False))
        .options(selectinload(IpAsset.patent), selectinload(IpAsset.copyright))
        .order_by(sort_group, grant_date.desc(), IpAsset.updated_at.desc())
    )
    if query.q:
        stmt = stmt.where(
            or_(
                IpAsset.name.ilike(f"%{query.q}%"),
                IpAsset.docket_no.ilike(f"%{query.q}%"),
            )
        )
    if query.ip_type:
        stmt = stmt.where(IpAsset.ip_type == query.ip_type)
    if query.status_group:
        stmt = stmt.where(IpAsset.status_group == query.status_group)
    if query.project_id:
        stmt = stmt.where(IpAsset.project_id == query.project_id)
    if query.owner_user_id:
        stmt = stmt.where(IpAsset.owner_user_id == query.owner_user_id)

    rows, total = paginate(db, stmt, page=page, page_size=page_size)
    return Page[AssetListItem](
        items=[AssetListItem.model_validate(row) for row in rows], total=total, page=page, page_size=page_size
    )


@router.get("/{asset_id}", response_model=AssetDetail)
def get_asset(
    asset_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AssetDetail:
    asset = ensure_asset_visible(_load_asset(db, asset_id), user)
    return _asset_detail(db, asset)


@router.post("", response_model=AssetDetail, status_code=status.HTTP_201_CREATED)
def create_asset(
    payload: AssetCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_write),
) -> AssetDetail:
    ensure_type_payload(payload.ip_type, payload.patent, payload.copyright, payload.trademark)

    asset = IpAsset(
        name=payload.name,
        docket_no=payload.docket_no,
        ip_type=payload.ip_type,
        status_group=payload.status_group,
        project_id=payload.project_id,
        owner_user_id=payload.owner_user_id,
        remark=payload.remark,
        created_by=user.id,
        updated_by=user.id,
    )
    db.add(asset)
    db.flush()

    if payload.ip_type == IpType.PATENT:
        db.add(Patent(ip_asset_id=asset.id, **(payload.patent.model_dump() if payload.patent else {})))
    elif payload.ip_type == IpType.COPYRIGHT:
        db.add(
            Copyright(
                ip_asset_id=asset.id,
                **(payload.copyright.model_dump() if payload.copyright else {}),
            )
        )
    else:
        db.add(
            Trademark(
                ip_asset_id=asset.id,
                **(payload.trademark.model_dump() if payload.trademark else {}),
            )
        )

    parties = list(payload.parties)
    if payload.ip_type == IpType.COPYRIGHT and payload.copyright_owner is not None:
        # 软著创建时权利人随档案在同一事务内创建并关联，避免“先建权利人再建档案”的两步非事务。
        party = Party(**payload.copyright_owner.model_dump(), created_by=user.id, updated_by=user.id)
        db.add(party)
        db.flush()
        parties.append(AssetPartyIn(party_id=party.id, role="copyright_owner", seq=0))
    _replace_relations(db, asset.id, parties, payload.persons)
    write_audit(
        db,
        user=user,
        action="create",
        object_type="ip_asset",
        object_id=asset.id,
        summary=asset.name,
        detail={"ip_type": asset.ip_type.value},
        request=request,
    )
    db.commit()
    return _asset_detail(db, _load_asset(db, asset.id))


@router.patch("/{asset_id}", response_model=AssetDetail)
def update_asset(
    asset_id: str,
    payload: AssetUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_write),
) -> AssetDetail:
    asset = ensure_asset_visible(_load_asset(db, asset_id), user)

    data = payload.model_dump(exclude_unset=True)
    professional = {
        "patent": data.pop("patent", None),
        "copyright": data.pop("copyright", None),
        "trademark": data.pop("trademark", None),
    }
    parties = data.pop("parties", None)
    persons = data.pop("persons", None)

    ensure_type_payload(
        asset.ip_type, professional["patent"], professional["copyright"], professional["trademark"]
    )

    for field, value in data.items():
        setattr(asset, field, value)
    asset.updated_by = user.id

    if professional["patent"]:
        if asset.patent is None:
            db.add(Patent(ip_asset_id=asset.id, **professional["patent"], created_by=user.id, updated_by=user.id))
        else:
            for field, value in professional["patent"].items():
                setattr(asset.patent, field, value)
            asset.patent.updated_by = user.id
    if professional["copyright"]:
        if asset.copyright is None:
            db.add(Copyright(ip_asset_id=asset.id, **professional["copyright"], created_by=user.id, updated_by=user.id))
        else:
            for field, value in professional["copyright"].items():
                setattr(asset.copyright, field, value)
            asset.copyright.updated_by = user.id
    if professional["trademark"]:
        if asset.trademark is None:
            db.add(Trademark(ip_asset_id=asset.id, **professional["trademark"], created_by=user.id, updated_by=user.id))
        else:
            for field, value in professional["trademark"].items():
                setattr(asset.trademark, field, value)
            asset.trademark.updated_by = user.id

    if parties is not None or persons is not None:
        _replace_relations(
            db,
            asset.id,
            payload.parties if parties is not None else None,
            payload.persons if persons is not None else None,
        )

    write_audit(
        db,
        user=user,
        action="update",
        object_type="ip_asset",
        object_id=asset.id,
        summary=asset.name,
        detail={"fields": sorted(data.keys())},
        request=request,
    )
    db.commit()
    return _asset_detail(db, _load_asset(db, asset.id))


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_asset(
    asset_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_write),
) -> None:
    asset = ensure_asset_visible(_load_asset(db, asset_id), user)
    # 逻辑删除，保留历史与审计线索。
    asset.is_deleted = True
    asset.updated_by = user.id
    write_audit(
        db,
        user=user,
        action="delete",
        object_type="ip_asset",
        object_id=asset.id,
        summary=asset.name,
        request=request,
    )
    db.commit()


def _replace_relations(db: Session, asset_id: str, parties, persons) -> None:
    if parties is not None:
        for item in parties:
            party = db.get(Party, item.party_id)
            if party is None or party.is_deleted:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"权利人不存在: {item.party_id}")
        db.execute(delete(AssetParty).where(AssetParty.ip_asset_id == asset_id))
        for item in parties:
            db.add(AssetParty(ip_asset_id=asset_id, party_id=item.party_id, role=item.role, seq=item.seq))
    if persons is not None:
        for item in persons:
            person = db.get(Person, item.person_id)
            if person is None or person.is_deleted:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"人员不存在: {item.person_id}")
        db.execute(delete(AssetPerson).where(AssetPerson.ip_asset_id == asset_id))
        for item in persons:
            db.add(AssetPerson(ip_asset_id=asset_id, person_id=item.person_id, role=item.role, seq=item.seq))
