"""系统管理接口：用户、审计日志与数据导入导出。

导入/导出均受权限控制并写入审计。导出只包含档案主数据，不含附件内容。
"""

from __future__ import annotations

import csv
import datetime
import io
from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import security
from app.database import get_db
from app.deps import get_current_user, require_admin, require_write, utcnow
from app.domain import (
    IMPORT_COLUMNS,
    derive_fee_status,
    missing_import_columns,
    parse_import_rows,
)
from app.models import (
    AssetParty,
    AssetStatus,
    AuditLog,
    AuthSession,
    Copyright,
    Fee,
    FeeType,
    IpAsset,
    IpType,
    Party,
    Patent,
    Trademark,
    User,
    UserRole,
)
from app.schemas import AuditLogOut, ImportResult, ImportRowError, Page, UserCreate, UserOut, UserUpdate
from app.services import paginate, write_audit

router = APIRouter(tags=["系统管理"])

EXPORT_COLUMNS = [
    "name",
    "ip_type",
    "status_group",
    "created_at",
    "updated_at",
]

@router.get("/users", response_model=Page[UserOut])
def list_users(
    q: str | None = Query(default=None, max_length=64),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> Page[UserOut]:
    stmt = select(User).where(User.is_deleted.is_(False))
    if q:
        stmt = stmt.where(or_(User.username.ilike(f"%{q}%"), User.display_name.ilike(f"%{q}%")))
    rows, total = paginate(db, stmt.order_by(User.username), page=page, page_size=page_size)
    return Page[UserOut](
        items=[UserOut.model_validate(row) for row in rows], total=total, page=page, page_size=page_size
    )


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> UserOut:
    if db.scalar(select(User.id).where(User.username == payload.username, User.is_deleted.is_(False))):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="账号已存在")

    user = User(
        username=payload.username,
        display_name=payload.display_name,
        password_hash=security.hash_password(payload.password),
        role=payload.role,
        email=payload.email,
        phone=payload.phone,
        created_by=admin.id,
        updated_by=admin.id,
    )
    db.add(user)
    # 审计只记录账号与角色，不记录密码。
    write_audit(
        db,
        user=admin,
        action="create",
        object_type="user",
        object_id=user.id,
        summary=f"{user.username} ({user.role.value})",
        request=request,
    )
    db.commit()
    return UserOut.model_validate(user)


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: str,
    payload: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> UserOut:
    user = db.get(User, user_id)
    if user is None or user.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    data = payload.model_dump(exclude_unset=True)
    if user.id == admin.id:
        # 与前端一致：服务端也要阻止管理员把自己降权或停用，避免账号自锁。
        if data.get("role") is not None and data["role"] != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="不能修改当前登录账号的角色",
            )
        if data.get("is_active") is False:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="不能停用当前登录账号",
            )
    password = data.pop("password", None)
    if password:
        user.password_hash = security.hash_password(password)
    for field, value in data.items():
        setattr(user, field, value)
    user.updated_by = admin.id

    write_audit(
        db,
        user=admin,
        action="update",
        object_type="user",
        object_id=user.id,
        summary=user.username,
        detail={"fields": sorted(list(data.keys()) + (["password"] if password else []))},
        request=request,
    )
    db.commit()
    return UserOut.model_validate(user)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_user(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> None:
    user = db.get(User, user_id)
    if user is None or user.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    if user.id == admin.id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="不能删除当前登录账号")

    user.is_deleted = True
    user.is_active = False
    user.updated_by = admin.id
    now = utcnow()
    sessions = db.scalars(
        select(AuthSession).where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
    ).all()
    for item in sessions:
        item.revoked_at = now
    write_audit(
        db,
        user=admin,
        action="delete",
        object_type="user",
        object_id=user.id,
        summary=user.username,
        request=request,
    )
    db.commit()


@router.get("/audit-logs", response_model=Page[AuditLogOut])
def list_audit_logs(
    object_type: str | None = Query(default=None, max_length=64),
    object_id: str | None = Query(default=None, max_length=36),
    action: str | None = Query(default=None, max_length=32),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> Page[AuditLogOut]:
    stmt = select(AuditLog)
    if object_type:
        stmt = stmt.where(AuditLog.object_type == object_type)
    if object_id:
        stmt = stmt.where(AuditLog.object_id == object_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    rows, total = paginate(db, stmt.order_by(AuditLog.created_at.desc()), page=page, page_size=page_size)
    return Page[AuditLogOut](
        items=[AuditLogOut.model_validate(row) for row in rows], total=total, page=page, page_size=page_size
    )


@router.get("/export/assets.csv")
def export_assets(
    request: Request,
    ip_type: IpType | None = None,
    status_group: AssetStatus | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    stmt = select(IpAsset).where(IpAsset.is_deleted.is_(False))
    if ip_type:
        stmt = stmt.where(IpAsset.ip_type == ip_type)
    if status_group:
        stmt = stmt.where(IpAsset.status_group == status_group)

    buffer = io.StringIO()
    # BOM 便于 Excel 正确识别 UTF-8 中文。
    buffer.write("\ufeff")
    writer = csv.writer(buffer)
    writer.writerow(EXPORT_COLUMNS)
    for asset in db.scalars(stmt.order_by(IpAsset.created_at, IpAsset.id)).all():
        writer.writerow(
            [
                asset.name,
                asset.ip_type.value,
                asset.status_group.value,
                asset.created_at.isoformat() if asset.created_at else "",
                asset.updated_at.isoformat() if asset.updated_at else "",
            ]
        )

    write_audit(
        db,
        user=user,
        action="export",
        object_type="ip_asset",
        summary=f"导出档案 {ip_type.value if ip_type else 'all'}",
        request=request,
    )
    db.commit()

    buffer.seek(0)
    filename = f"ip-assets-{datetime.date.today().isoformat()}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/assets.xlsx")
def export_assets_xlsx(
    request: Request,
    ip_type: IpType | None = None,
    status_group: AssetStatus | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出 Excel（xlsx）。未安装 openpyxl 时返回 503，而不是给出损坏文件。"""

    try:
        from openpyxl import Workbook
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="服务器未安装 openpyxl，无法导出 Excel；请联系管理员或改用 CSV 导出",
        ) from None

    stmt = select(IpAsset).where(IpAsset.is_deleted.is_(False))
    if ip_type:
        stmt = stmt.where(IpAsset.ip_type == ip_type)
    if status_group:
        stmt = stmt.where(IpAsset.status_group == status_group)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "知识产权档案"
    sheet.append(["名称", "类型", "综合状态", "创建时间", "更新时间"])
    for asset in db.scalars(stmt.order_by(IpAsset.created_at, IpAsset.id)).all():
        sheet.append(
            [
                asset.name,
                asset.ip_type.value,
                asset.status_group.value,
                asset.created_at.isoformat() if asset.created_at else "",
                asset.updated_at.isoformat() if asset.updated_at else "",
            ]
        )

    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)

    write_audit(
        db,
        user=user,
        action="export",
        object_type="ip_asset",
        summary=f"导出 Excel 档案 {ip_type.value if ip_type else 'all'}",
        request=request,
    )
    db.commit()

    filename = f"ip-assets-{datetime.date.today().isoformat()}.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/import/assets/template.xlsx")
def download_import_template(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_write),
) -> StreamingResponse:
    try:
        from openpyxl import Workbook
    except ImportError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="服务器未安装 openpyxl") from None
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "档案导入"
    sheet.append(list(IMPORT_COLUMNS))
    guide = workbook.create_sheet("填写说明")
    guide.append(["列名", "是否必填", "说明"])
    for column, required, note in (
        ("我方文号", "否", "企业内部案件文号，保存到档案的 docket_no"),
        ("申请号", "否", "导入到专利档案的申请号"),
        ("案件名称", "是", "唯一必填列"),
        ("专利所有权人", "否", "按名称匹配已有权利人；不存在时自动创建，并关联为专利权人"),
        ("官费应缴纳日", "否", "日期格式 YYYY-MM-DD"),
        ("本次官费缴纳至", "否", "本次缴费覆盖至的日期，格式 YYYY-MM-DD"),
        ("本次官费缴纳金额", "否", "最多两位小数，默认币种 CNY"),
        ("缴纳日期", "否", "实际缴纳日期，格式 YYYY-MM-DD"),
    ):
        guide.append([column, required, note])
    guide.append([])
    guide.append(["说明", "", "空白可选列不会创建对应数据。"])
    buffer = io.BytesIO(); workbook.save(buffer); buffer.seek(0)
    write_audit(db, user=user, action="download_template", object_type="ip_asset", summary="下载 XLSX 导入模板", request=request)
    db.commit()
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="ip-assets-import-template.xlsx"'},
    )


def _resolve_patentee(db: Session, name: str, user: User) -> Party:
    """按名称复用已有权利人；不存在时创建企业类型权利人。"""

    party = db.scalar(
        select(Party)
        .where(Party.name == name, Party.is_deleted.is_(False))
        .order_by(Party.created_at)
        .limit(1)
    )
    if party is None:
        party = Party(name=name, created_by=user.id, updated_by=user.id)
        db.add(party)
        db.flush()
    return party


@router.post("/import/assets", response_model=ImportResult)
def import_assets(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_write),
) -> ImportResult:
    raw = file.file.read()
    if not raw:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="文件为空")

    filename = (file.filename or "").lower()
    if filename.endswith(".xlsx"):
        try:
            from openpyxl import load_workbook
        except ImportError:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="服务器未安装 openpyxl") from None
        try:
            workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
            sheet = workbook.worksheets[0]
            values = list(sheet.iter_rows(values_only=True))
        except Exception:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="无法读取 XLSX 文件") from None
        if not values:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="工作表为空")
        fieldnames = [str(value or "").strip() for value in values[0]]
        rows = [
            {fieldnames[index]: "" if value is None else str(value) for index, value in enumerate(row) if index < len(fieldnames)}
            for row in values[1:]
            if any(value not in (None, "") for value in row)
        ]
    elif filename.endswith(".csv"):
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="CSV 必须使用 UTF-8 编码"
            ) from None
        reader = csv.DictReader(io.StringIO(text))
        fieldnames = [(name or "").strip() for name in (reader.fieldnames or [])]
        reader.fieldnames = fieldnames
        rows = list(reader)
    else:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="仅支持 CSV 或 XLSX 文件")
    missing = missing_import_columns(fieldnames)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"缺少必需列：{', '.join(missing)}",
        )

    accepted, row_errors = parse_import_rows(rows)
    errors = [ImportRowError(row=row_number, message=message) for row_number, message in row_errors]
    skipped = len(errors)
    created = 0

    for parsed in accepted:
        ip_type = IpType(str(parsed["ip_type"]))
        docket_no = parsed["docket_no"]
        application_no = parsed["application_no"]
        asset = IpAsset(
            name=str(parsed["name"]),
            docket_no=str(docket_no) if docket_no else None,
            ip_type=ip_type,
            status_group=AssetStatus(str(parsed["status_group"])),
            created_by=user.id,
            updated_by=user.id,
        )
        db.add(asset)
        db.flush()
        professional_application_no = str(application_no) if application_no else None
        if ip_type == IpType.PATENT:
            db.add(Patent(ip_asset_id=asset.id, application_no=professional_application_no))
        elif ip_type == IpType.COPYRIGHT:
            db.add(Copyright(ip_asset_id=asset.id))
        else:
            db.add(Trademark(ip_asset_id=asset.id, application_no=professional_application_no))

        patentee = parsed["patentee"]
        if patentee:
            party = _resolve_patentee(db, str(patentee), user)
            db.add(AssetParty(ip_asset_id=asset.id, party_id=party.id, role="patentee", seq=0))

        fee_amount = parsed["fee_amount"]
        fee_due_date = parsed["fee_due_date"]
        fee_coverage_end_date = parsed["fee_coverage_end_date"]
        fee_paid_date = parsed["fee_paid_date"]
        if any(
            value is not None
            for value in (fee_amount, fee_due_date, fee_coverage_end_date, fee_paid_date)
        ):
            # ASSUMPTION: 模板未区分应缴/实缴金额，将「本次官费缴纳金额」同时作为
            # 应缴和实缴金额；空白金额记为 0.00 且未缴，避免丢失应缴日与缴至日。
            amount_due = fee_amount if isinstance(fee_amount, Decimal) else Decimal("0.00")
            amount_paid = fee_amount if isinstance(fee_amount, Decimal) else None
            # ASSUMPTION: 「本次官费缴纳至」对应年费覆盖期，费用类型按年费导入。
            db.add(
                Fee(
                    ip_asset_id=asset.id,
                    fee_type=FeeType.ANNUITY,
                    description="官费",
                    amount_due=amount_due,
                    amount_paid=amount_paid,
                    currency="CNY",
                    due_date=fee_due_date,
                    paid_date=fee_paid_date,
                    coverage_end_date=fee_coverage_end_date,
                    status=derive_fee_status(amount_due, amount_paid),
                    created_by=user.id,
                    updated_by=user.id,
                )
            )
        created += 1

    write_audit(
        db,
        user=user,
        action="import",
        object_type="ip_asset",
        summary=f"导入 {created} 条，跳过 {skipped} 条",
        request=request,
    )
    db.commit()

    return ImportResult(total_rows=created + skipped, created=created, skipped=skipped, errors=errors)
