"""已授权、已登记、已注册证书：电子证书与纸质原件状态分开记录。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_write
from app.models import (
    Certificate,
    CertificateType,
    IpAsset,
    PaperCertStatus,
    User,
)
from app.schemas import (
    CertificateIn,
    CertificateOut,
    Page,
)
from app.services import ensure_asset_visible, ensure_material_reference, paginate, scoped_related, write_audit

router = APIRouter(tags=["证书"])


@router.get("/certificates", response_model=Page[CertificateOut])
def list_certificates(
    q: str | None = Query(default=None, max_length=128),
    cert_type: CertificateType | None = None,
    paper_status: PaperCertStatus | None = None,
    ip_asset_id: str | None = None,
    include_deleted_parent: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Page[CertificateOut]:
    stmt = scoped_related(
        select(Certificate).where(Certificate.is_deleted.is_(False)),
        Certificate.ip_asset_id,
        user,
        include_deleted_parent=include_deleted_parent,
    )
    if q:
        stmt = stmt.where(Certificate.cert_no.ilike(f"%{q}%"))
    if cert_type:
        stmt = stmt.where(Certificate.cert_type == cert_type)
    if paper_status:
        stmt = stmt.where(Certificate.paper_status == paper_status)
    if ip_asset_id:
        ensure_asset_visible(db.get(IpAsset, ip_asset_id), user)
        stmt = stmt.where(Certificate.ip_asset_id == ip_asset_id)

    rows, total = paginate(db, stmt.order_by(Certificate.issue_date.desc().nulls_last()), page=page, page_size=page_size)
    return Page[CertificateOut](
        items=[CertificateOut.model_validate(row) for row in rows], total=total, page=page, page_size=page_size
    )


@router.post("/certificates", response_model=CertificateOut, status_code=status.HTTP_201_CREATED)
def create_certificate(
    payload: CertificateIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_write),
) -> CertificateOut:
    ensure_asset_visible(db.get(IpAsset, payload.ip_asset_id), user)
    ensure_material_reference(
        db, payload.file_material_id, payload.ip_asset_id, user, field_label="电子证书附件"
    )
    certificate = Certificate(
        **payload.model_dump(), created_by=user.id, updated_by=user.id
    )
    db.add(certificate)
    write_audit(
        db,
        user=user,
        action="create",
        object_type="certificate",
        object_id=certificate.id,
        summary=certificate.cert_no,
        request=request,
    )
    db.commit()
    return CertificateOut.model_validate(certificate)


@router.patch("/certificates/{certificate_id}", response_model=CertificateOut)
def update_certificate(
    certificate_id: str,
    payload: CertificateIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_write),
) -> CertificateOut:
    certificate = db.get(Certificate, certificate_id)
    if certificate is None or certificate.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="证书不存在")
    ensure_asset_visible(db.get(IpAsset, certificate.ip_asset_id), user)
    ensure_asset_visible(db.get(IpAsset, payload.ip_asset_id), user)
    ensure_material_reference(
        db, payload.file_material_id, payload.ip_asset_id, user, field_label="电子证书附件"
    )

    for field, value in payload.model_dump().items():
        setattr(certificate, field, value)
    certificate.updated_by = user.id
    write_audit(
        db,
        user=user,
        action="update",
        object_type="certificate",
        object_id=certificate.id,
        summary=certificate.cert_no,
        request=request,
    )
    db.commit()
    return CertificateOut.model_validate(certificate)
