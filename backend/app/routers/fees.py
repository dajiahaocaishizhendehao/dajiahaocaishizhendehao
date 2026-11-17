"""费用与发票。

应付、实付、发票金额分别保存，不相互推算；统计口径由调用方显式选择。
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app import extraction_tasks
from app.constants import ExtractionStatus
from app.database import get_db
from app.deps import get_current_user, require_write
from app.domain import DomainError, derive_fee_status
from app.models import Fee, FeeStatus, FeeType, Invoice, InvoiceFee, IpAsset, Material, MaterialFlag, Patent, User
from app.schemas import FeeIn, FeeOut, InvoiceIn, InvoiceOut, Page
from app.config import get_settings
from app.domain import DomainError, validate_upload
from app.services import (
    ensure_asset_visible,
    ensure_invoice_fees,
    ensure_material_reference,
    ensure_related_visible,
    paginate,
    scoped_asset_ids,
    scoped_related,
    write_audit,
)
from app.storage import get_storage

router = APIRouter(tags=["费用与发票"])


def _derive_fee_status(amount_due: Decimal, amount_paid: Decimal | None, explicit: FeeStatus | None) -> FeeStatus:
    """包装 domain 规则，把业务异常转换为 HTTP 422。"""

    try:
        return derive_fee_status(amount_due, amount_paid, explicit)
    except DomainError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from None


def _fee_audit_summary(fee: Fee, *, with_currency: bool = True) -> str:
    """审计摘要固定两位小数，避免不同数据库对 Numeric 标度的处理不一致。"""

    amount = fee.amount_due.quantize(Decimal("0.01"))
    return f"{fee.fee_type.value} {amount} {fee.currency}" if with_currency else f"{fee.fee_type.value} {amount}"


@router.get("/fees", response_model=Page[FeeOut])
def list_fees(
    q: str | None = Query(default=None, max_length=128),
    ip_asset_id: str | None = None,
    fee_type: FeeType | None = None,
    status_filter: FeeStatus | None = Query(default=None, alias="status"),
    include_deleted_parent: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Page[FeeOut]:
    stmt = scoped_related(
        select(Fee).where(Fee.is_deleted.is_(False)),
        Fee.ip_asset_id,
        user,
        include_deleted_parent=include_deleted_parent,
    )
    if q:
        pattern = f"%{q}%"
        matching_assets = scoped_asset_ids(user).where(
            or_(IpAsset.name.ilike(pattern), IpAsset.docket_no.ilike(pattern))
        )
        matching_patents = select(Patent.ip_asset_id).where(Patent.application_no.ilike(pattern))
        stmt = stmt.where(
            or_(
                Fee.description.ilike(pattern),
                Fee.ip_asset_id.in_(matching_assets),
                Fee.ip_asset_id.in_(matching_patents),
            )
        )
    if ip_asset_id:
        ensure_asset_visible(db.get(IpAsset, ip_asset_id), user)
        stmt = stmt.where(Fee.ip_asset_id == ip_asset_id)
    if fee_type:
        stmt = stmt.where(Fee.fee_type == fee_type)
    if status_filter:
        stmt = stmt.where(Fee.status == status_filter)

    rows, total = paginate(db, stmt.order_by(Fee.due_date.asc().nulls_last()), page=page, page_size=page_size)
    items = _with_asset_info(db, rows)
    return Page[FeeOut](items=items, total=total, page=page, page_size=page_size)


def _with_asset_info(db: Session, rows: list[Fee]) -> list[FeeOut]:
    """补充案件名称/文号，让费用台账以「案件名称」为主展示。"""

    asset_ids = {row.ip_asset_id for row in rows if row.ip_asset_id}
    assets: dict[str, IpAsset] = {}
    patents: dict[str, Patent] = {}
    if asset_ids:
        for asset in db.scalars(select(IpAsset).where(IpAsset.id.in_(asset_ids))).all():
            assets[asset.id] = asset
        for patent in db.scalars(select(Patent).where(Patent.ip_asset_id.in_(asset_ids))).all():
            patents[patent.ip_asset_id] = patent

    items: list[FeeOut] = []
    for row in rows:
        item = FeeOut.model_validate(row)
        asset = assets.get(row.ip_asset_id) if row.ip_asset_id else None
        if asset is not None:
            item.asset_name = asset.name
            item.docket_no = asset.docket_no
        patent = patents.get(row.ip_asset_id) if row.ip_asset_id else None
        if patent is not None:
            item.application_no = patent.application_no
        items.append(item)

    fee_ids = [row.id for row in rows]
    if fee_ids:
        counts = dict(
            db.execute(
                select(InvoiceFee.fee_id, func.count(InvoiceFee.invoice_id))
                .join(Invoice, Invoice.id == InvoiceFee.invoice_id)
                .where(InvoiceFee.fee_id.in_(fee_ids), Invoice.is_deleted.is_(False))
                .group_by(InvoiceFee.fee_id)
            ).all()
        )
        for item in items:
            item.invoice_count = counts.get(item.id, 0)

    return items


@router.post("/fees", response_model=FeeOut, status_code=status.HTTP_201_CREATED)
def create_fee(
    payload: FeeIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_write),
) -> FeeOut:
    if payload.ip_asset_id:
        ensure_asset_visible(db.get(IpAsset, payload.ip_asset_id), user)
    ensure_material_reference(
        db, payload.voucher_material_id, payload.ip_asset_id, user, field_label="费用凭证"
    )
    data = payload.model_dump()
    explicit = data.pop("status", None)
    data["status"] = _derive_fee_status(payload.amount_due, payload.amount_paid, explicit)

    fee = Fee(**data, created_by=user.id, updated_by=user.id)
    db.add(fee)
    db.flush()
    write_audit(
        db,
        user=user,
        action="create",
        object_type="fee",
        object_id=fee.id,
        summary=_fee_audit_summary(fee),
        request=request,
    )
    db.commit()
    return FeeOut.model_validate(fee)


@router.patch("/fees/{fee_id}", response_model=FeeOut)
def update_fee(
    fee_id: str,
    payload: FeeIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_write),
) -> FeeOut:
    fee = db.get(Fee, fee_id)
    if fee is None or fee.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="费用不存在")
    ensure_related_visible(db, fee.ip_asset_id, user, detail="费用不存在")
    if payload.ip_asset_id:
        ensure_asset_visible(db.get(IpAsset, payload.ip_asset_id), user)
    ensure_material_reference(
        db, payload.voucher_material_id, payload.ip_asset_id, user, field_label="费用凭证"
    )

    data = payload.model_dump()
    explicit = data.pop("status", None)
    data["status"] = _derive_fee_status(payload.amount_due, payload.amount_paid, explicit)
    for field, value in data.items():
        setattr(fee, field, value)
    fee.updated_by = user.id

    write_audit(
        db,
        user=user,
        action="update",
        object_type="fee",
        object_id=fee.id,
        summary=_fee_audit_summary(fee),
        request=request,
    )
    db.commit()
    return FeeOut.model_validate(fee)


@router.delete("/fees/{fee_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_fee(
    fee_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_write),
) -> None:
    fee = db.get(Fee, fee_id)
    if fee is None or fee.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="费用不存在")
    ensure_related_visible(db, fee.ip_asset_id, user, detail="费用不存在")

    fee.is_deleted = True
    fee.updated_by = user.id
    write_audit(
        db,
        user=user,
        action="delete",
        object_type="fee",
        object_id=fee.id,
        summary=_fee_audit_summary(fee, with_currency=False),
        request=request,
    )
    db.commit()


@router.post("/invoices/recognize")
def recognize_invoice(
    request: Request,
    file: UploadFile = File(...),
    ip_asset_id: str | None = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_write),
) -> dict:
    """上传发票附件：保存为材料并识别票面信息。

    附件立即入库（可在材料中心看到），识别结果仅作为建议值返回。
    """

    settings = get_settings()
    if ip_asset_id:
        ensure_asset_visible(db.get(IpAsset, ip_asset_id), user)

    original_name = (file.filename or "").strip()
    content = file.file.read(settings.max_upload_bytes + 1)
    try:
        suffix = validate_upload(
            original_name,
            file.content_type,
            len(content),
            content=content,
            allowed_mimes=settings.allowed_mime_types,
            max_bytes=settings.max_upload_bytes,
        )
    except DomainError as error:
        message = str(error)
        code = (
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
            if "大小限制" in message
            else status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
            if "类型" in message
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(status_code=code, detail=message) from None

    storage = get_storage()
    stored = storage.save(content, suffix=suffix)
    try:
        material = Material(
            ip_asset_id=ip_asset_id,
            category="invoice",
            display_name=original_name[:255],
            storage_key=stored.storage_key,
            original_name=original_name[:255],
            ext=suffix.lstrip(".")[:16] or None,
            mime_type=(file.content_type or "")[:128] or None,
            size_bytes=stored.size_bytes,
            sha256=stored.sha256,
            flag=MaterialFlag.NORMAL,
            extraction_status=ExtractionStatus.PENDING,
            extraction_kind="invoice",
            uploaded_by=user.id,
            created_by=user.id,
            updated_by=user.id,
        )
        db.add(material)
        db.flush()
        write_audit(
            db,
            user=user,
            action="recognize_invoice",
            object_type="invoice",
            object_id=material.id,
            summary=original_name,
            request=request,
        )
        db.commit()
    except Exception:
        db.rollback()
        storage.delete(stored.storage_key)
        raise

    extraction_tasks.submit_extraction(material.id, "invoice")
    return {
        "material_id": material.id,
        "status": material.extraction_status.value,
        "fields": {},
        "warnings": [],
        "preview": f"/api/materials/{material.id}/preview",
    }


@router.get("/fees/{fee_id}", response_model=FeeOut)
def get_fee(
    fee_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FeeOut:
    """费用详情（含案件名称与发票张数）。"""

    row = db.get(Fee, fee_id)
    if row is None or row.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="费用不存在")
    if row.ip_asset_id:
        ensure_asset_visible(db.get(IpAsset, row.ip_asset_id), user)

    items = _with_asset_info(db, [row])
    return items[0]


@router.get("/fees/{fee_id}/invoices", response_model=Page[InvoiceOut])
def list_fee_invoices(
    fee_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Page[InvoiceOut]:
    """某笔费用关联的发票（发票作为费用详情的一部分展示）。"""

    fee = db.get(Fee, fee_id)
    if fee is None or fee.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="费用不存在")
    if fee.ip_asset_id:
        ensure_asset_visible(db.get(IpAsset, fee.ip_asset_id), user)

    invoice_ids = select(InvoiceFee.invoice_id).where(InvoiceFee.fee_id == fee_id)
    stmt = select(Invoice).where(Invoice.is_deleted.is_(False), Invoice.id.in_(invoice_ids))
    rows, total = paginate(db, stmt.order_by(Invoice.invoice_date.desc().nulls_last()), page=page, page_size=page_size)

    asset_ids = {row.ip_asset_id for row in rows if row.ip_asset_id}
    assets: dict[str, IpAsset] = {}
    if asset_ids:
        for asset in db.scalars(select(IpAsset).where(IpAsset.id.in_(asset_ids))).all():
            assets[asset.id] = asset

    fee_map: dict[str, list[str]] = {}
    invoice_ids = [row.id for row in rows]
    if invoice_ids:
        for invoice_id, fee_id in db.execute(
            select(InvoiceFee.invoice_id, InvoiceFee.fee_id).where(InvoiceFee.invoice_id.in_(invoice_ids))
        ).all():
            fee_map.setdefault(invoice_id, []).append(fee_id)

    items: list[InvoiceOut] = []
    for row in rows:
        item = InvoiceOut.model_validate(row)
        item.fee_ids = fee_map.get(row.id, [])
        asset = assets.get(row.ip_asset_id) if row.ip_asset_id else None
        if asset is not None:
            item.asset_name = asset.name
            item.docket_no = asset.docket_no
        items.append(item)
    return Page[InvoiceOut](items=items, total=total, page=page, page_size=page_size)


@router.post("/fees/{fee_id}/invoices/{invoice_id}", status_code=status.HTTP_201_CREATED)
def link_fee_invoice(
    fee_id: str,
    invoice_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_write),
) -> dict:
    """把已有发票关联到某笔费用。"""

    fee = db.get(Fee, fee_id)
    if fee is None or fee.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="费用不存在")
    ensure_related_visible(db, fee.ip_asset_id, user, detail="费用不存在")
    invoice = db.get(Invoice, invoice_id)
    if invoice is None or invoice.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="发票不存在")
    ensure_related_visible(db, invoice.ip_asset_id, user, detail="发票不存在")
    if fee.ip_asset_id != invoice.ip_asset_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="发票与费用必须属于同一案件",
        )

    exists = db.scalar(
        select(InvoiceFee).where(InvoiceFee.fee_id == fee_id, InvoiceFee.invoice_id == invoice_id)
    )
    if exists is None:
        db.add(InvoiceFee(invoice_id=invoice_id, fee_id=fee_id))

    write_audit(
        db,
        user=user,
        action="link_invoice",
        object_type="fee",
        object_id=fee_id,
        summary=invoice.invoice_no,
        request=request,
    )
    db.commit()
    return {"fee_id": fee_id, "invoice_id": invoice_id}


@router.get("/invoices", response_model=Page[InvoiceOut])
def list_invoices(
    q: str | None = Query(default=None, max_length=128),
    ip_asset_id: str | None = None,
    include_deleted_parent: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Page[InvoiceOut]:
    """发票列表。支持按案件筛选，以及按案件名称/我方文号/发票号/开票单位搜索。"""

    stmt = scoped_related(
        select(Invoice).where(Invoice.is_deleted.is_(False)),
        Invoice.ip_asset_id,
        user,
        include_deleted_parent=include_deleted_parent,
    )
    if ip_asset_id:
        ensure_asset_visible(db.get(IpAsset, ip_asset_id), user)
        stmt = stmt.where(Invoice.ip_asset_id == ip_asset_id)
    if q:
        pattern = f"%{q}%"
        asset_ids = [
            row
            for row in db.scalars(
                scoped_asset_ids(user).where(
                    or_(IpAsset.name.ilike(pattern), IpAsset.docket_no.ilike(pattern))
                )
            ).all()
        ]
        conditions = [
            Invoice.invoice_no.ilike(pattern),
            Invoice.issuer.ilike(pattern),
            Invoice.buyer.ilike(pattern),
        ]
        if asset_ids:
            conditions.append(Invoice.ip_asset_id.in_(asset_ids))
        stmt = stmt.where(or_(*conditions))

    rows, total = paginate(db, stmt.order_by(Invoice.invoice_date.desc().nulls_last()), page=page, page_size=page_size)

    assets: dict[str, IpAsset] = {}
    asset_ids = {row.ip_asset_id for row in rows if row.ip_asset_id}
    if asset_ids:
        for asset in db.scalars(select(IpAsset).where(IpAsset.id.in_(asset_ids))).all():
            assets[asset.id] = asset

    fee_map: dict[str, list[str]] = {}
    invoice_ids = [row.id for row in rows]
    if invoice_ids:
        for invoice_id, fee_id in db.execute(
            select(InvoiceFee.invoice_id, InvoiceFee.fee_id).where(InvoiceFee.invoice_id.in_(invoice_ids))
        ).all():
            fee_map.setdefault(invoice_id, []).append(fee_id)

    items: list[InvoiceOut] = []
    for row in rows:
        item = InvoiceOut.model_validate(row)
        item.fee_ids = fee_map.get(row.id, [])
        asset = assets.get(row.ip_asset_id) if row.ip_asset_id else None
        if asset is not None:
            item.asset_name = asset.name
            item.docket_no = asset.docket_no
        items.append(item)
    return Page[InvoiceOut](items=items, total=total, page=page, page_size=page_size)


@router.post("/invoices", response_model=InvoiceOut, status_code=status.HTTP_201_CREATED)
def create_invoice(
    payload: InvoiceIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_write),
) -> InvoiceOut:
    data = payload.model_dump()
    fee_ids = data.pop("fee_ids", [])
    if data.get("ip_asset_id"):
        ensure_asset_visible(db.get(IpAsset, data["ip_asset_id"]), user)
    ensure_material_reference(
        db, data.get("file_material_id"), data.get("ip_asset_id"), user, field_label="发票附件"
    )
    valid_fees = ensure_invoice_fees(db, fee_ids, data.get("ip_asset_id"), user)
    invoice = Invoice(**data, created_by=user.id, updated_by=user.id)
    db.add(invoice)
    db.flush()

    for fee in valid_fees:
        db.add(InvoiceFee(invoice_id=invoice.id, fee_id=fee.id))

    write_audit(
        db,
        user=user,
        action="create",
        object_type="invoice",
        object_id=invoice.id,
        summary=invoice.invoice_no,
        request=request,
    )
    db.commit()

    result = InvoiceOut.model_validate(invoice)
    result.fee_ids = [fee.id for fee in valid_fees]
    return result


@router.patch("/invoices/{invoice_id}", response_model=InvoiceOut)
def update_invoice(
    invoice_id: str,
    payload: InvoiceIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_write),
) -> InvoiceOut:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None or invoice.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="发票不存在")
    ensure_related_visible(db, invoice.ip_asset_id, user, detail="发票不存在")

    data = payload.model_dump()
    if data.get("ip_asset_id"):
        ensure_asset_visible(db.get(IpAsset, data["ip_asset_id"]), user)
    fee_ids = data.pop("fee_ids", None)
    for field, value in data.items():
        setattr(invoice, field, value)
    invoice.updated_by = user.id

    ensure_material_reference(
        db, invoice.file_material_id, invoice.ip_asset_id, user, field_label="发票附件"
    )
    if fee_ids is not None:
        valid_fees = ensure_invoice_fees(db, fee_ids, invoice.ip_asset_id, user)
        db.execute(delete(InvoiceFee).where(InvoiceFee.invoice_id == invoice.id))
        for fee in valid_fees:
            db.add(InvoiceFee(invoice_id=invoice.id, fee_id=fee.id))

    write_audit(
        db,
        user=user,
        action="update",
        object_type="invoice",
        object_id=invoice.id,
        summary=invoice.invoice_no,
        request=request,
    )
    db.commit()

    result = InvoiceOut.model_validate(invoice)
    result.fee_ids = list(db.scalars(select(InvoiceFee.fee_id).where(InvoiceFee.invoice_id == invoice.id)).all())
    return result
