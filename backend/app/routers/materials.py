"""电子材料：上传、查询、下载与逻辑删除。

文件二进制存于存储层，数据库只保存元数据、对象键、哈希与版本信息。
"""

from __future__ import annotations

import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import extraction_tasks
from app.config import get_settings
from app.database import get_db
from app.deps import get_current_user, require_write
from app.domain import DomainError, validate_upload
from app.models import ExtractionStatus, IpAsset, Material, MaterialFlag, User
from app.schemas import MaterialOut, MaterialUpdate, Page
from app.services import ensure_asset_visible, ensure_related_visible, paginate, scoped_related, write_audit
from app.storage import StoredFile, get_storage

router = APIRouter(prefix="/materials", tags=["电子材料"])

RECOGNIZABLE_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "webp"}


def ensure_recognizable(material: Material) -> None:
    ext = (material.ext or "").strip().lower().lstrip(".")
    if not ext and material.original_name:
        ext = material.original_name.rsplit(".", 1)[-1].lower()
    if ext not in RECOGNIZABLE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="该文件类型不支持识别，仅支持 PDF 和图片",
        )


@router.get("", response_model=Page[MaterialOut])
def list_materials(
    q: str | None = Query(default=None, max_length=128),
    ip_asset_id: str | None = None,
    category: str | None = None,
    flag: MaterialFlag | None = None,
    include_deleted_parent: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Page[MaterialOut]:
    stmt = scoped_related(
        select(Material).where(Material.is_deleted.is_(False)),
        Material.ip_asset_id,
        user,
        include_deleted_parent=include_deleted_parent,
    )
    if q:
        stmt = stmt.where(or_(Material.display_name.ilike(f"%{q}%"), Material.original_name.ilike(f"%{q}%")))
    if ip_asset_id:
        ensure_asset_visible(db.get(IpAsset, ip_asset_id), user)
        stmt = stmt.where(Material.ip_asset_id == ip_asset_id)
    if category:
        stmt = stmt.where(Material.category == category)
    if flag:
        stmt = stmt.where(Material.flag == flag)

    rows, total = paginate(db, stmt.order_by(Material.created_at.desc()), page=page, page_size=page_size)
    items = _with_asset_info(db, rows)
    return Page[MaterialOut](items=items, total=total, page=page, page_size=page_size)


def _with_asset_info(db: Session, rows: list[Material]) -> list[MaterialOut]:
    """补充案件名称与我方文号，让材料按案件名称关联展示。"""

    asset_ids = {row.ip_asset_id for row in rows if row.ip_asset_id}
    assets: dict[str, IpAsset] = {}
    if asset_ids:
        for asset in db.scalars(select(IpAsset).where(IpAsset.id.in_(asset_ids))).all():
            assets[asset.id] = asset

    items: list[MaterialOut] = []
    for row in rows:
        item = MaterialOut.model_validate(row)
        asset = assets.get(row.ip_asset_id) if row.ip_asset_id else None
        if asset is not None:
            item.asset_name = asset.name
            item.docket_no = asset.docket_no
        items.append(item)
    return items


def _validate_and_store(file: UploadFile) -> tuple[str, str | None, str, StoredFile]:
    """校验上传文件并写入存储层，返回原始文件名、MIME、扩展名与存储结果。"""

    settings = get_settings()
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
    return original_name, file.content_type, suffix, get_storage().save(content, suffix=suffix)


@router.post("", response_model=MaterialOut, status_code=status.HTTP_201_CREATED)
def upload_material(
    request: Request,
    file: UploadFile = File(...),
    category: str = Form(..., min_length=1, max_length=64),
    ip_asset_id: str | None = Form(default=None),
    display_name: str | None = Form(default=None, max_length=255),
    file_date: datetime.date | None = Form(default=None),
    version: str | None = Form(default=None, max_length=32),
    flag: MaterialFlag = Form(default=MaterialFlag.NORMAL),
    remark: str | None = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_write),
) -> MaterialOut:
    if ip_asset_id:
        ensure_asset_visible(db.get(IpAsset, ip_asset_id), user)

    original_name, content_type, suffix, stored = _validate_and_store(file)

    storage = get_storage()
    try:
        material = Material(
            ip_asset_id=ip_asset_id,
            category=category,
            display_name=(display_name or original_name)[:255],
            storage_key=stored.storage_key,
            original_name=original_name[:255],
            ext=suffix.lstrip(".")[:16] or None,
            mime_type=(content_type or "")[:128] or None,
            size_bytes=stored.size_bytes,
            sha256=stored.sha256,
            file_date=file_date,
            version=version,
            flag=flag,
            remark=remark,
            uploaded_by=user.id,
            created_by=user.id,
            updated_by=user.id,
        )
        db.add(material)
        db.flush()
        write_audit(
            db,
            user=user,
            action="upload",
            object_type="material",
            object_id=material.id,
            summary=material.display_name,
            detail={"size_bytes": material.size_bytes, "sha256": material.sha256},
            request=request,
        )
        db.commit()
        return MaterialOut.model_validate(material)
    except Exception:
        db.rollback()
        storage.delete(stored.storage_key)
        raise


@router.patch("/{material_id}", response_model=MaterialOut)
def update_material(
    material_id: str,
    payload: MaterialUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_write),
) -> MaterialOut:
    material = db.get(Material, material_id)
    if material is None or material.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="材料不存在")
    ensure_related_visible(db, material.ip_asset_id, user, detail="材料不存在")

    data = payload.model_dump(exclude_unset=True)
    if data.get("ip_asset_id"):
        ensure_asset_visible(db.get(IpAsset, data["ip_asset_id"]), user)

    for field, value in data.items():
        setattr(material, field, value)
    material.updated_by = user.id
    write_audit(
        db,
        user=user,
        action="update",
        object_type="material",
        object_id=material.id,
        summary=material.display_name,
        request=request,
    )
    db.commit()
    return MaterialOut.model_validate(material)


@router.post("/{material_id}/replace", response_model=MaterialOut)
def replace_material_file(
    material_id: str,
    request: Request,
    file: UploadFile = File(...),
    remark: str | None = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_write),
) -> MaterialOut:
    """更换材料文件，可同时更新备注。

    旧文件按已确认的保留策略留在存储层，仅解除数据库引用；审计日志记录旧对象键与哈希，
    便于追溯或人工恢复。
    """

    material = db.get(Material, material_id)
    if material is None or material.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="材料不存在")
    ensure_related_visible(db, material.ip_asset_id, user, detail="材料不存在")

    original_name, content_type, suffix, stored = _validate_and_store(file)
    old_file = {
        "storage_key": material.storage_key,
        "sha256": material.sha256,
        "size_bytes": material.size_bytes,
        "original_name": material.original_name,
    }

    try:
        # 显示名称未被人为修改时，跟随新文件名。
        if material.display_name == material.original_name:
            material.display_name = original_name[:255] or material.display_name
        material.original_name = original_name[:255]
        material.storage_key = stored.storage_key
        material.ext = suffix.lstrip(".")[:16] or None
        material.mime_type = (content_type or "")[:128] or None
        material.size_bytes = stored.size_bytes
        material.sha256 = stored.sha256
        if remark is not None:
            material.remark = remark or None
        # 文件已更换，旧文件的识别结果不再适用于新文件。
        material.extraction_status = ExtractionStatus.NONE
        material.extraction_kind = None
        material.extraction_source = None
        material.extraction_fields = None
        material.extraction_text = None
        material.extraction_error = None
        material.extraction_started_at = None
        material.extraction_finished_at = None
        material.updated_by = user.id
        write_audit(
            db,
            user=user,
            action="replace_file",
            object_type="material",
            object_id=material.id,
            summary=material.display_name,
            detail={
                "old": old_file,
                "new": {
                    "storage_key": material.storage_key,
                    "sha256": material.sha256,
                    "size_bytes": material.size_bytes,
                    "original_name": material.original_name,
                },
            },
            request=request,
        )
        db.commit()
        return MaterialOut.model_validate(material)
    except Exception:
        db.rollback()
        get_storage().delete(stored.storage_key)
        raise


@router.delete("/{material_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_material(
    material_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_write),
) -> None:
    material = db.get(Material, material_id)
    if material is None or material.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="材料不存在")
    ensure_related_visible(db, material.ip_asset_id, user, detail="材料不存在")
    material.is_deleted = True
    material.updated_by = user.id
    write_audit(
        db,
        user=user,
        action="delete",
        object_type="material",
        object_id=material.id,
        summary=material.display_name,
        request=request,
    )
    db.commit()


@router.get("/{material_id}/preview")
def preview_material(
    material_id: str,
    page: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """返回材料预览图：PDF 按页码渲染，图片原样返回。

    PDF 响应头 X-Page-Count 返回总页数；图片固定为 1 页。
    """

    material = db.get(Material, material_id)
    if material is None or material.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="材料不存在")
    ensure_related_visible(db, material.ip_asset_id, user, detail="材料不存在")

    storage = get_storage()
    if not storage.exists(material.storage_key):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="文件已不可用")
    path = storage.root / material.storage_key
    suffix = (material.ext or "").lower()

    if suffix in {"png", "jpg", "jpeg", "webp"}:
        media = "image/jpeg" if suffix in {"jpg", "jpeg"} else f"image/{suffix}"
        return Response(
            content=path.read_bytes(),
            media_type=media,
            headers={"X-Page-Count": "1"},
        )

    if suffix == "pdf":
        try:
            import pymupdf
        except ImportError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="服务器未安装 pymupdf，无法生成预览"
            ) from None
        document = pymupdf.open(path)
        try:
            page_count = document.page_count
            if page_count == 0:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="PDF 没有可预览页面")
            if page >= page_count:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="页码超出范围")
            pixmap = document[page].get_pixmap(dpi=110)
            data = pixmap.tobytes("png")
        finally:
            document.close()
        return Response(
            content=data,
            media_type="image/png",
            headers={"X-Page-Count": str(page_count), "X-Page-Index": str(page)},
        )

    raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="该文件类型不支持预览")


@router.post("/{material_id}/extract")
def extract_material(
    material_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_write),
) -> dict:
    """识别证书/通知扫描件中的关键字段。

    只返回建议值，不写入任何档案字段；确认后由前端调用档案更新接口。
    """

    material = db.get(Material, material_id)
    if material is None or material.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="材料不存在")
    ensure_related_visible(db, material.ip_asset_id, user, detail="材料不存在")

    storage = get_storage()
    if not storage.exists(material.storage_key):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="文件已不可用")
    ensure_recognizable(material)

    material.extraction_status = ExtractionStatus.PENDING
    material.extraction_kind = "certificate"
    material.extraction_source = None
    material.extraction_fields = None
    material.extraction_text = None
    material.extraction_error = None
    material.extraction_started_at = None
    material.extraction_finished_at = None
    write_audit(
        db,
        user=user,
        action="extract",
        object_type="material",
        object_id=material.id,
        summary=f"{material.display_name}（后台识别）",
        request=request,
    )
    db.commit()
    extraction_tasks.submit_extraction(material.id, "certificate")

    return {
        "material_id": material.id,
        "status": material.extraction_status.value,
        "source": None,
        "text": "",
        "fields": {},
        "warnings": [],
        "needs_review": True,
    }


@router.post("/{material_id}/extract-invoice")
def extract_invoice_material(
    material_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_write),
) -> dict:
    """复用已保存的附件重新执行发票识别，不重复上传文件。"""

    material = db.get(Material, material_id)
    if material is None or material.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="材料不存在")
    ensure_related_visible(db, material.ip_asset_id, user, detail="材料不存在")
    if not get_storage().exists(material.storage_key):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="文件已不可用")
    ensure_recognizable(material)

    material.extraction_status = ExtractionStatus.PENDING
    material.extraction_kind = "invoice"
    material.extraction_source = None
    material.extraction_fields = None
    material.extraction_text = None
    material.extraction_error = None
    material.extraction_started_at = None
    material.extraction_finished_at = None
    write_audit(
        db,
        user=user,
        action="extract",
        object_type="material",
        object_id=material.id,
        summary=f"{material.display_name}（重新识别发票）",
        request=request,
    )
    db.commit()
    extraction_tasks.submit_extraction(material.id, "invoice")
    return {"material_id": material.id, "status": material.extraction_status.value}


@router.get("/{material_id}/extraction")
def get_extraction(
    material_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    material = db.get(Material, material_id)
    if material is None or material.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="材料不存在")
    ensure_related_visible(db, material.ip_asset_id, user, detail="材料不存在")
    payload = material.extraction_fields or {}
    return {
        "material_id": material.id,
        "status": material.extraction_status.value,
        "source": material.extraction_source,
        "text": material.extraction_text or "",
        "fields": payload.get("fields", {}),
        "warnings": payload.get("warnings", []),
        "error": material.extraction_error,
        "needs_review": True,
    }


@router.get("/{material_id}/download")
def download_material(
    material_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    material = db.get(Material, material_id)
    if material is None or material.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="材料不存在")
    ensure_related_visible(db, material.ip_asset_id, user, detail="材料不存在")

    storage = get_storage()
    if not storage.exists(material.storage_key):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="文件已不可用")
    content = storage.read(material.storage_key)

    write_audit(
        db,
        user=user,
        action="download",
        object_type="material",
        object_id=material.id,
        summary=material.display_name,
        request=request,
    )
    db.commit()

    filename = quote(material.original_name)
    return Response(
        content=content,
        media_type=material.mime_type or "application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )
