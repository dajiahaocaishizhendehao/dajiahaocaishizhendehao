"""ORM 数据模型。

建模约定（对应 AGENTS.md 第 6 节）：
- 专利、软著、商标共享 ip_assets 主档，专业字段分别存放于独立表；
- 材料、日期、费用、发票、证书均通过 ip_asset_id 关联主档；
- 金额使用 Numeric 定点类型并保存币种；
- 业务日期使用 Date，操作时间使用带时区 DateTime；
- 删除采用逻辑删除（is_deleted），不物理删除业务数据。
"""

from __future__ import annotations

import datetime
import enum
import uuid
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def new_id() -> str:
    return str(uuid.uuid4())


# 枚举定义移至 app.constants，便于脱离 ORM 进行业务规则测试。
from app.constants import (  # noqa: E402  (紧随包导入，保持命名空间可复用)
    AssetStatus,
    CertificateType,
    DateSource,
    DateStatus,
    DateType,
    ElectronicCertStatus,
    ExtractionStatus,
    FeeStatus,
    FeeType,
    InvoiceOriginalStatus,
    IpType,
    MarkType,
    MaterialFlag,
    PaperCertStatus,
    PartyType,
    PatentType,
    PersonType,
    ReimbursementStatus,
    UserRole,
)


def enum_column(py_enum: type[enum.Enum], name: str) -> SAEnum:
    """生成带 CHECK 约束的字符串枚举列，避免数据库依赖原生枚举类型。"""

    return SAEnum(
        py_enum,
        name=name,
        native_enum=False,
        length=32,
        values_callable=lambda items: [item.value for item in items],
        validate_strings=True,
    )


# --------------------------------------------------------------------------
# 公共 Mixin
# --------------------------------------------------------------------------


class IdMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)


class AuditMixin:
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    created_by: Mapped[str | None] = mapped_column(String(36))
    updated_by: Mapped[str | None] = mapped_column(String(36))
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)


# --------------------------------------------------------------------------
# 组织与基础资料
# --------------------------------------------------------------------------


class User(IdMixin, AuditMixin, Base):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(enum_column(UserRole, "user_role"), nullable=False)
    email: Mapped[str | None] = mapped_column(String(160))
    phone: Mapped[str | None] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AuthSession(IdMixin, Base):
    """不透明会话令牌，令牌原文不入库，只保存哈希。"""

    __tablename__ = "auth_sessions"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Agency(IdMixin, AuditMixin, Base):
    __tablename__ = "agencies"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    contact: Mapped[str | None] = mapped_column(String(64))
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(160))
    address: Mapped[str | None] = mapped_column(String(255))
    service_type: Mapped[str | None] = mapped_column(String(64))
    remark: Mapped[str | None] = mapped_column(Text)


class Project(IdMixin, AuditMixin, Base):
    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    code: Mapped[str | None] = mapped_column(String(64), unique=True)
    owner_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    start_date: Mapped[datetime.date | None] = mapped_column(Date)
    status: Mapped[str | None] = mapped_column(String(32))
    remark: Mapped[str | None] = mapped_column(Text)

    # 只读展示用：基础资料列表需要显示负责人姓名，而不是用户 ID。
    owner_user: Mapped[User | None] = relationship(foreign_keys=[owner_user_id], lazy="joined")

    @property
    def owner_display_name(self) -> str | None:
        return self.owner_user.display_name if self.owner_user else None


class Party(IdMixin, AuditMixin, Base):
    """权利人：专利申请人/专利权人、著作权人、商标注册人。"""

    __tablename__ = "parties"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    party_type: Mapped[PartyType] = mapped_column(
        enum_column(PartyType, "party_type"), nullable=False, default=PartyType.COMPANY
    )
    id_number: Mapped[str | None] = mapped_column(String(64))
    country: Mapped[str | None] = mapped_column(String(64))
    address: Mapped[str | None] = mapped_column(String(255))
    contact: Mapped[str | None] = mapped_column(String(64))
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(160))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Person(IdMixin, AuditMixin, Base):
    """发明人、设计人、开发人员、联系人。"""

    __tablename__ = "persons"

    name: Mapped[str] = mapped_column(String(64), nullable=False)
    employee_no: Mapped[str | None] = mapped_column(String(64))
    person_type: Mapped[PersonType] = mapped_column(
        enum_column(PersonType, "person_type"), nullable=False, default=PersonType.INVENTOR
    )
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(160))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


# --------------------------------------------------------------------------
# 知识产权主档
# --------------------------------------------------------------------------


class IpAsset(IdMixin, AuditMixin, Base):
    """知识产权主档：专利、软著、商标共用。"""

    __tablename__ = "ip_assets"
    __table_args__ = (
        CheckConstraint("length(name) > 0", name="ck_ip_assets_name_not_blank"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # 我方文号：企业内部案件编号（如 STHL2001-1-A36NF），与实际台账保持一致。
    docket_no: Mapped[str | None] = mapped_column(String(64), index=True)
    ip_type: Mapped[IpType] = mapped_column(enum_column(IpType, "ip_type"), nullable=False, index=True)
    status_group: Mapped[AssetStatus] = mapped_column(
        enum_column(AssetStatus, "asset_status"), nullable=False, default=AssetStatus.IN_PROGRESS, index=True
    )
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"))
    owner_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    remark: Mapped[str | None] = mapped_column(Text)

    patent: Mapped[Patent | None] = relationship(
        back_populates="asset", uselist=False, cascade="all, delete-orphan"
    )
    copyright: Mapped[Copyright | None] = relationship(
        back_populates="asset", uselist=False, cascade="all, delete-orphan"
    )
    trademark: Mapped[Trademark | None] = relationship(
        back_populates="asset", uselist=False, cascade="all, delete-orphan"
    )

    @property
    def grant_date(self) -> datetime.date | None:
        """统一列表展示用：专利取授权公告日，软著取证书日期（界面同样显示为授权公告日），商标返回空。"""

        if self.patent is not None:
            return self.patent.grant_date
        if self.copyright is not None:
            return self.copyright.certificate_date
        return None


class AssetParty(IdMixin, Base):
    __tablename__ = "asset_parties"
    __table_args__ = (UniqueConstraint("ip_asset_id", "party_id", "role", name="uq_asset_party_role"),)

    ip_asset_id: Mapped[str] = mapped_column(ForeignKey("ip_assets.id"), nullable=False, index=True)
    party_id: Mapped[str] = mapped_column(ForeignKey("parties.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class AssetPerson(IdMixin, Base):
    __tablename__ = "asset_persons"
    __table_args__ = (UniqueConstraint("ip_asset_id", "person_id", "role", name="uq_asset_person_role"),)

    ip_asset_id: Mapped[str] = mapped_column(ForeignKey("ip_assets.id"), nullable=False, index=True)
    person_id: Mapped[str] = mapped_column(ForeignKey("persons.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


# --------------------------------------------------------------------------
# 专业档案
# --------------------------------------------------------------------------


class Patent(IdMixin, AuditMixin, Base):
    __tablename__ = "patents"

    ip_asset_id: Mapped[str] = mapped_column(
        ForeignKey("ip_assets.id"), unique=True, nullable=False, index=True
    )
    patent_type: Mapped[PatentType] = mapped_column(
        enum_column(PatentType, "patent_type"), nullable=False, default=PatentType.INVENTION
    )
    summary: Mapped[str | None] = mapped_column(Text)
    tech_field: Mapped[str | None] = mapped_column(String(160))
    country: Mapped[str | None] = mapped_column(String(64))
    application_no: Mapped[str | None] = mapped_column(String(64), index=True)
    application_date: Mapped[datetime.date | None] = mapped_column(Date)
    publication_no: Mapped[str | None] = mapped_column(String(64))
    publication_date: Mapped[datetime.date | None] = mapped_column(Date)
    patent_no: Mapped[str | None] = mapped_column(String(64), index=True)
    grant_date: Mapped[datetime.date | None] = mapped_column(Date)
    expiry_date: Mapped[datetime.date | None] = mapped_column(Date)
    legal_status: Mapped[str | None] = mapped_column(String(64))
    agency_id: Mapped[str | None] = mapped_column(ForeignKey("agencies.id"))
    agent_name: Mapped[str | None] = mapped_column(String(64))

    asset: Mapped[IpAsset] = relationship(back_populates="patent")


class Copyright(IdMixin, AuditMixin, Base):
    __tablename__ = "copyrights"

    ip_asset_id: Mapped[str] = mapped_column(
        ForeignKey("ip_assets.id"), unique=True, nullable=False, index=True
    )
    short_name: Mapped[str | None] = mapped_column(String(160))
    version: Mapped[str | None] = mapped_column(String(32))
    category: Mapped[str | None] = mapped_column(String(64))
    purpose: Mapped[str | None] = mapped_column(Text)
    tech_features: Mapped[str | None] = mapped_column(Text)
    dev_language: Mapped[str | None] = mapped_column(String(120))
    platform: Mapped[str | None] = mapped_column(String(120))
    dev_completed_date: Mapped[datetime.date | None] = mapped_column(Date)
    dev_mode: Mapped[str | None] = mapped_column(String(64))
    rights_mode: Mapped[str | None] = mapped_column(String(64))
    is_published: Mapped[bool | None] = mapped_column(Boolean)
    first_publish_date: Mapped[datetime.date | None] = mapped_column(Date)
    first_publish_place: Mapped[str | None] = mapped_column(String(160))
    application_date: Mapped[datetime.date | None] = mapped_column(Date)
    acceptance_date: Mapped[datetime.date | None] = mapped_column(Date)
    registration_no: Mapped[str | None] = mapped_column(String(64), index=True)
    registration_date: Mapped[datetime.date | None] = mapped_column(Date)
    certificate_no: Mapped[str | None] = mapped_column(String(64))
    certificate_date: Mapped[datetime.date | None] = mapped_column(Date)
    correction_date: Mapped[datetime.date | None] = mapped_column(Date)
    correction_due_date: Mapped[datetime.date | None] = mapped_column(Date)
    agency_id: Mapped[str | None] = mapped_column(ForeignKey("agencies.id"))

    asset: Mapped[IpAsset] = relationship(back_populates="copyright")


class Trademark(IdMixin, AuditMixin, Base):
    __tablename__ = "trademarks"

    ip_asset_id: Mapped[str] = mapped_column(
        ForeignKey("ip_assets.id"), unique=True, nullable=False, index=True
    )
    word_mark: Mapped[str | None] = mapped_column(String(160))
    logo_material_id: Mapped[str | None] = mapped_column(ForeignKey("materials.id"))
    mark_type: Mapped[MarkType] = mapped_column(
        enum_column(MarkType, "mark_type"), nullable=False, default=MarkType.COMBINED
    )
    color_desc: Mapped[str | None] = mapped_column(String(160))
    country: Mapped[str | None] = mapped_column(String(64))
    application_no: Mapped[str | None] = mapped_column(String(64), index=True)
    application_date: Mapped[datetime.date | None] = mapped_column(Date)
    registration_no: Mapped[str | None] = mapped_column(String(64), index=True)
    registration_date: Mapped[datetime.date | None] = mapped_column(Date)
    valid_from: Mapped[datetime.date | None] = mapped_column(Date)
    valid_to: Mapped[datetime.date | None] = mapped_column(Date)
    classes: Mapped[list | None] = mapped_column(JSON)
    agency_id: Mapped[str | None] = mapped_column(ForeignKey("agencies.id"))
    agent_name: Mapped[str | None] = mapped_column(String(64))

    asset: Mapped[IpAsset] = relationship(back_populates="trademark")


# --------------------------------------------------------------------------
# 材料（电子文件）
# --------------------------------------------------------------------------


class Material(IdMixin, AuditMixin, Base):
    __tablename__ = "materials"
    __table_args__ = (
        UniqueConstraint("storage_key", name="uq_materials_storage_key"),
        CheckConstraint("size_bytes >= 0", name="ck_materials_size"),
    )

    ip_asset_id: Mapped[str | None] = mapped_column(ForeignKey("ip_assets.id"), index=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    ext: Mapped[str | None] = mapped_column(String(16))
    mime_type: Mapped[str | None] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    file_date: Mapped[datetime.date | None] = mapped_column(Date)
    version: Mapped[str | None] = mapped_column(String(32))
    flag: Mapped[MaterialFlag] = mapped_column(
        enum_column(MaterialFlag, "material_flag"), nullable=False, default=MaterialFlag.NORMAL
    )
    remark: Mapped[str | None] = mapped_column(Text)
    extraction_status: Mapped[ExtractionStatus] = mapped_column(
        enum_column(ExtractionStatus, "extraction_status"), nullable=False, default=ExtractionStatus.NONE
    )
    extraction_kind: Mapped[str | None] = mapped_column(String(32))
    extraction_source: Mapped[str | None] = mapped_column(String(32))
    extraction_fields: Mapped[dict | None] = mapped_column(JSON)
    extraction_text: Mapped[str | None] = mapped_column(Text)
    extraction_error: Mapped[str | None] = mapped_column(String(500))
    extraction_started_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    extraction_finished_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    uploaded_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))


# --------------------------------------------------------------------------
# 证书
# --------------------------------------------------------------------------


class Certificate(IdMixin, AuditMixin, Base):
    __tablename__ = "certificates"

    ip_asset_id: Mapped[str] = mapped_column(ForeignKey("ip_assets.id"), nullable=False, index=True)
    cert_type: Mapped[CertificateType] = mapped_column(
        enum_column(CertificateType, "certificate_type"), nullable=False
    )
    cert_no: Mapped[str | None] = mapped_column(String(64))
    issue_date: Mapped[datetime.date | None] = mapped_column(Date)
    electronic_status: Mapped[ElectronicCertStatus] = mapped_column(
        enum_column(ElectronicCertStatus, "electronic_cert_status"),
        nullable=False,
        default=ElectronicCertStatus.PENDING,
    )
    file_material_id: Mapped[str | None] = mapped_column(ForeignKey("materials.id"))
    paper_status: Mapped[PaperCertStatus] = mapped_column(
        enum_column(PaperCertStatus, "paper_cert_status"),
        nullable=False,
        default=PaperCertStatus.NOT_RECEIVED,
    )
    received_date: Mapped[datetime.date | None] = mapped_column(Date)
    keeper: Mapped[str | None] = mapped_column(String(64))
    location: Mapped[str | None] = mapped_column(String(128))
    recipient: Mapped[str | None] = mapped_column(String(64))
    recipient_date: Mapped[datetime.date | None] = mapped_column(Date)
    remark: Mapped[str | None] = mapped_column(Text)


# --------------------------------------------------------------------------
# 日期事项
# --------------------------------------------------------------------------


class DateItem(IdMixin, AuditMixin, Base):
    """日期事项。

    计划日期、截止日期、实际完成日期、提醒时间分开存放；系统不推导法律期限。
    """

    __tablename__ = "date_items"

    ip_asset_id: Mapped[str | None] = mapped_column(ForeignKey("ip_assets.id"), index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    date_type: Mapped[DateType] = mapped_column(enum_column(DateType, "date_type"), nullable=False)
    planned_date: Mapped[datetime.date | None] = mapped_column(Date)
    due_date: Mapped[datetime.date | None] = mapped_column(Date, index=True)
    actual_date: Mapped[datetime.date | None] = mapped_column(Date)
    remind_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[DateSource] = mapped_column(
        enum_column(DateSource, "date_source"), nullable=False, default=DateSource.MANUAL
    )
    rule_version: Mapped[str | None] = mapped_column(String(64))
    needs_confirmation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[DateStatus] = mapped_column(
        enum_column(DateStatus, "date_status"), nullable=False, default=DateStatus.OPEN
    )
    owner_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    remark: Mapped[str | None] = mapped_column(Text)


# --------------------------------------------------------------------------
# 费用与发票
# --------------------------------------------------------------------------


class Fee(IdMixin, AuditMixin, Base):
    __tablename__ = "fees"
    __table_args__ = (
        CheckConstraint("amount_due >= 0", name="ck_fees_amount_due"),
        CheckConstraint("amount_paid IS NULL OR amount_paid >= 0", name="ck_fees_amount_paid"),
    )

    ip_asset_id: Mapped[str | None] = mapped_column(ForeignKey("ip_assets.id"), index=True)
    fee_type: Mapped[FeeType] = mapped_column(enum_column(FeeType, "fee_type"), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    amount_due: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    amount_paid: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="CNY")
    due_date: Mapped[datetime.date | None] = mapped_column(Date, index=True)
    paid_date: Mapped[datetime.date | None] = mapped_column(Date)
    # 本次缴费覆盖至（年费专用）：表示缴到哪一天，与应缴日、实缴日区分开。
    coverage_end_date: Mapped[datetime.date | None] = mapped_column(Date, index=True)
    payee: Mapped[str | None] = mapped_column(String(160))
    payer: Mapped[str | None] = mapped_column(String(160))
    payment_method: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[FeeStatus] = mapped_column(
        enum_column(FeeStatus, "fee_status"), nullable=False, default=FeeStatus.UNPAID
    )
    voucher_material_id: Mapped[str | None] = mapped_column(ForeignKey("materials.id"))
    handler: Mapped[str | None] = mapped_column(String(64))
    remark: Mapped[str | None] = mapped_column(Text)


class Invoice(IdMixin, AuditMixin, Base):
    __tablename__ = "invoices"
    __table_args__ = (
        CheckConstraint("amount_net IS NULL OR amount_net >= 0", name="ck_invoices_net"),
        CheckConstraint("tax_amount IS NULL OR tax_amount >= 0", name="ck_invoices_tax"),
        CheckConstraint("amount_gross IS NULL OR amount_gross >= 0", name="ck_invoices_gross"),
    )

    # 发票归属案件：发票是“某件专利/软著/商标的申请或年费支出凭证”。
    ip_asset_id: Mapped[str | None] = mapped_column(ForeignKey("ip_assets.id"), index=True)

    invoice_no: Mapped[str] = mapped_column(String(64), nullable=False)
    invoice_code: Mapped[str | None] = mapped_column(String(32))
    invoice_type: Mapped[str | None] = mapped_column(String(32))
    issuer: Mapped[str | None] = mapped_column(String(160))
    buyer: Mapped[str | None] = mapped_column(String(160))
    invoice_date: Mapped[datetime.date | None] = mapped_column(Date)
    amount_net: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    tax_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    amount_gross: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="CNY")
    reimbursement_status: Mapped[ReimbursementStatus] = mapped_column(
        enum_column(ReimbursementStatus, "reimbursement_status"),
        nullable=False,
        default=ReimbursementStatus.NOT_SUBMITTED,
    )
    reimbursement_date: Mapped[datetime.date | None] = mapped_column(Date)
    original_status: Mapped[InvoiceOriginalStatus] = mapped_column(
        enum_column(InvoiceOriginalStatus, "invoice_original_status"),
        nullable=False,
        default=InvoiceOriginalStatus.IN_STORAGE,
    )
    file_material_id: Mapped[str | None] = mapped_column(ForeignKey("materials.id"))
    remark: Mapped[str | None] = mapped_column(Text)


class InvoiceFee(IdMixin, Base):
    """发票与费用多对多关联。"""

    __tablename__ = "invoice_fees"
    __table_args__ = (UniqueConstraint("invoice_id", "fee_id", name="uq_invoice_fee"),)

    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id"), nullable=False, index=True)
    fee_id: Mapped[str] = mapped_column(ForeignKey("fees.id"), nullable=False, index=True)


# --------------------------------------------------------------------------
# 审计
# --------------------------------------------------------------------------


class AuditLog(IdMixin, Base):
    __tablename__ = "audit_logs"

    user_id: Mapped[str | None] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    object_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    object_id: Mapped[str | None] = mapped_column(String(36), index=True)
    summary: Mapped[str | None] = mapped_column(String(255))
    detail: Mapped[dict | None] = mapped_column(JSON)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
