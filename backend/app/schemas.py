"""Pydantic 请求/响应模型。

约束原则：必填与格式在接口层校验，业务唯一性与关联完整性在服务层校验。
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain import DomainError, ensure_date_order, validate_certificate_dates

# 枚举来自 constants 而非 models：接口契约层不应依赖 ORM，
# 这样在没有 SQLAlchemy 的环境中也能对请求/响应模型做真实校验。
from app.constants import (
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

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


# --------------------------------------------------------------------------
# 认证与用户
# --------------------------------------------------------------------------


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class UserOut(ORMModel):
    id: str
    username: str
    display_name: str
    role: UserRole
    email: str | None = None
    phone: str | None = None
    is_active: bool


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime.datetime
    user: UserOut


# --------------------------------------------------------------------------
# 基础资料
# --------------------------------------------------------------------------


class AgencyIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    contact: str | None = Field(default=None, max_length=64)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=160)
    address: str | None = Field(default=None, max_length=255)
    service_type: str | None = Field(default=None, max_length=64)
    remark: str | None = None


class AgencyOut(ORMModel):
    id: str
    name: str
    contact: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    service_type: str | None = None
    remark: str | None = None


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    code: str | None = Field(default=None, max_length=64)
    owner_user_id: str | None = None
    start_date: datetime.date | None = None
    status: str | None = Field(default=None, max_length=32)
    remark: str | None = None


class ProjectOut(ORMModel):
    id: str
    name: str
    code: str | None = None
    owner_user_id: str | None = None
    owner_display_name: str | None = None
    start_date: datetime.date | None = None
    status: str | None = None
    remark: str | None = None


class PartyIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    party_type: PartyType = PartyType.COMPANY
    id_number: str | None = Field(default=None, max_length=64)
    country: str | None = Field(default=None, max_length=64)
    address: str | None = Field(default=None, max_length=255)
    contact: str | None = Field(default=None, max_length=64)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=160)
    is_default: bool = False


class PartyOut(ORMModel):
    id: str
    name: str
    party_type: PartyType
    id_number: str | None = None
    country: str | None = None
    address: str | None = None
    contact: str | None = None
    phone: str | None = None
    email: str | None = None
    is_default: bool


class PersonIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    employee_no: str | None = Field(default=None, max_length=64)
    person_type: PersonType = PersonType.INVENTOR
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=160)
    is_active: bool = True


class PersonOut(ORMModel):
    id: str
    name: str
    employee_no: str | None = None
    person_type: PersonType
    is_active: bool


# --------------------------------------------------------------------------
# 专业档案
# --------------------------------------------------------------------------


class PatentIn(BaseModel):
    patent_type: PatentType = PatentType.INVENTION
    summary: str | None = None
    tech_field: str | None = Field(default=None, max_length=160)
    country: str | None = Field(default=None, max_length=64)
    application_no: str | None = Field(default=None, max_length=64)
    application_date: datetime.date | None = None
    publication_no: str | None = Field(default=None, max_length=64)
    publication_date: datetime.date | None = None
    patent_no: str | None = Field(default=None, max_length=64)
    grant_date: datetime.date | None = None
    expiry_date: datetime.date | None = None
    legal_status: str | None = Field(default=None, max_length=64)
    agency_id: str | None = None
    agent_name: str | None = Field(default=None, max_length=64)

    @field_validator("grant_date")
    @classmethod
    def grant_not_before_application(cls, value: datetime.date | None, info):
        try:
            ensure_date_order(info.data.get("application_date"), value, "授权日期不能早于申请日期")
        except DomainError as error:
            raise ValueError(str(error)) from None
        return value


class PatentOut(ORMModel):
    ip_asset_id: str
    patent_type: PatentType
    summary: str | None = None
    tech_field: str | None = None
    country: str | None = None
    application_no: str | None = None
    application_date: datetime.date | None = None
    publication_no: str | None = None
    publication_date: datetime.date | None = None
    patent_no: str | None = None
    grant_date: datetime.date | None = None
    expiry_date: datetime.date | None = None
    legal_status: str | None = None
    agency_id: str | None = None
    agent_name: str | None = None


class CopyrightIn(BaseModel):
    short_name: str | None = Field(default=None, max_length=160)
    version: str | None = Field(default=None, max_length=32)
    category: str | None = Field(default=None, max_length=64)
    purpose: str | None = None
    tech_features: str | None = None
    dev_language: str | None = Field(default=None, max_length=120)
    platform: str | None = Field(default=None, max_length=120)
    dev_completed_date: datetime.date | None = None
    dev_mode: str | None = Field(default=None, max_length=64)
    rights_mode: str | None = Field(default=None, max_length=64)
    is_published: bool | None = None
    first_publish_date: datetime.date | None = None
    first_publish_place: str | None = Field(default=None, max_length=160)
    application_date: datetime.date | None = None
    acceptance_date: datetime.date | None = None
    registration_no: str | None = Field(default=None, max_length=64)
    registration_date: datetime.date | None = None
    certificate_no: str | None = Field(default=None, max_length=64)
    certificate_date: datetime.date | None = None
    correction_date: datetime.date | None = None
    correction_due_date: datetime.date | None = None
    agency_id: str | None = None


class CopyrightOut(ORMModel):
    ip_asset_id: str
    short_name: str | None = None
    version: str | None = None
    category: str | None = None
    purpose: str | None = None
    tech_features: str | None = None
    dev_language: str | None = None
    platform: str | None = None
    dev_completed_date: datetime.date | None = None
    dev_mode: str | None = None
    rights_mode: str | None = None
    is_published: bool | None = None
    first_publish_date: datetime.date | None = None
    first_publish_place: str | None = None
    application_date: datetime.date | None = None
    acceptance_date: datetime.date | None = None
    registration_no: str | None = None
    registration_date: datetime.date | None = None
    certificate_no: str | None = None
    certificate_date: datetime.date | None = None
    correction_date: datetime.date | None = None
    correction_due_date: datetime.date | None = None
    agency_id: str | None = None


class TrademarkIn(BaseModel):
    word_mark: str | None = Field(default=None, max_length=160)
    logo_material_id: str | None = None
    mark_type: MarkType = MarkType.COMBINED
    color_desc: str | None = Field(default=None, max_length=160)
    country: str | None = Field(default=None, max_length=64)
    application_no: str | None = Field(default=None, max_length=64)
    application_date: datetime.date | None = None
    registration_no: str | None = Field(default=None, max_length=64)
    registration_date: datetime.date | None = None
    valid_from: datetime.date | None = None
    valid_to: datetime.date | None = None
    classes: list[str] | None = None
    agency_id: str | None = None
    agent_name: str | None = Field(default=None, max_length=64)

    @field_validator("valid_to")
    @classmethod
    def valid_range(cls, value: datetime.date | None, info):
        try:
            ensure_date_order(info.data.get("valid_from"), value, "有效期截止日期不能早于起始日期")
        except DomainError as error:
            raise ValueError(str(error)) from None
        return value


class TrademarkOut(ORMModel):
    ip_asset_id: str
    word_mark: str | None = None
    logo_material_id: str | None = None
    mark_type: MarkType
    color_desc: str | None = None
    country: str | None = None
    application_no: str | None = None
    application_date: datetime.date | None = None
    registration_no: str | None = None
    registration_date: datetime.date | None = None
    valid_from: datetime.date | None = None
    valid_to: datetime.date | None = None
    classes: list[str] | None = None
    agency_id: str | None = None
    agent_name: str | None = None


# --------------------------------------------------------------------------
# 知识产权主档
# --------------------------------------------------------------------------


class AssetPersonIn(BaseModel):
    person_id: str
    role: str = Field(min_length=1, max_length=32)
    seq: int = 0


class AssetPartyIn(BaseModel):
    party_id: str
    role: str = Field(min_length=1, max_length=32)
    seq: int = 0


class AssetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    docket_no: str | None = Field(default=None, max_length=64)
    ip_type: IpType
    status_group: AssetStatus = AssetStatus.IN_PROGRESS
    project_id: str | None = None
    owner_user_id: str | None = None
    remark: str | None = None
    patent: PatentIn | None = None
    copyright: CopyrightIn | None = None
    copyright_owner: PartyIn | None = None  # 仅软著：随档案原子创建权利人并关联
    trademark: TrademarkIn | None = None
    parties: list[AssetPartyIn] = []
    persons: list[AssetPersonIn] = []

    @field_validator("patent")
    @classmethod
    def _noop(cls, value):
        return value


class AssetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    docket_no: str | None = Field(default=None, max_length=64)
    status_group: AssetStatus | None = None
    project_id: str | None = None
    owner_user_id: str | None = None
    remark: str | None = None
    patent: PatentIn | None = None
    copyright: CopyrightIn | None = None
    trademark: TrademarkIn | None = None
    parties: list[AssetPartyIn] | None = None
    persons: list[AssetPersonIn] | None = None


class AssetListItem(ORMModel):
    id: str
    name: str
    docket_no: str | None = None
    ip_type: IpType
    status_group: AssetStatus
    owner_user_id: str | None = None
    grant_date: datetime.date | None = None
    updated_at: datetime.datetime


class AssetDetail(AssetListItem):
    project_id: str | None = None
    remark: str | None = None
    created_at: datetime.datetime
    patent: PatentOut | None = None
    copyright: CopyrightOut | None = None
    trademark: TrademarkOut | None = None
    parties: list[PartyOut] = []
    persons: list[PersonOut] = []


# --------------------------------------------------------------------------
# 材料
# --------------------------------------------------------------------------


class MaterialOut(ORMModel):
    id: str
    ip_asset_id: str | None = None
    # 以案件名称展示（列表按名称关联）
    asset_name: str | None = None
    docket_no: str | None = None
    category: str
    display_name: str
    original_name: str
    ext: str | None = None
    mime_type: str | None = None
    size_bytes: int
    sha256: str
    file_date: datetime.date | None = None
    version: str | None = None
    flag: MaterialFlag
    remark: str | None = None
    extraction_status: ExtractionStatus = ExtractionStatus.NONE
    extraction_kind: str | None = None
    extraction_source: str | None = None
    extraction_fields: dict | None = None
    extraction_error: str | None = None
    extraction_started_at: datetime.datetime | None = None
    extraction_finished_at: datetime.datetime | None = None
    uploaded_by: str | None = None
    created_at: datetime.datetime


class MaterialUpdate(BaseModel):
    ip_asset_id: str | None = None
    category: str | None = Field(default=None, max_length=64)
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    file_date: datetime.date | None = None
    version: str | None = Field(default=None, max_length=32)
    flag: MaterialFlag | None = None
    remark: str | None = None


# --------------------------------------------------------------------------
# 证书
# --------------------------------------------------------------------------


class CertificateIn(BaseModel):
    ip_asset_id: str
    cert_type: CertificateType
    cert_no: str | None = Field(default=None, max_length=64)
    issue_date: datetime.date | None = None
    electronic_status: ElectronicCertStatus = ElectronicCertStatus.PENDING
    file_material_id: str | None = None
    paper_status: PaperCertStatus = PaperCertStatus.NOT_RECEIVED
    received_date: datetime.date | None = None
    keeper: str | None = Field(default=None, max_length=64)
    location: str | None = Field(default=None, max_length=128)
    recipient: str | None = Field(default=None, max_length=64)
    recipient_date: datetime.date | None = None
    remark: str | None = None

    @field_validator("recipient_date")
    @classmethod
    def recipient_after_received(cls, value: datetime.date | None, info):
        try:
            validate_certificate_dates(info.data.get("received_date"), value)
        except DomainError as error:
            raise ValueError(str(error)) from None
        return value


class CertificateOut(ORMModel):
    id: str
    ip_asset_id: str
    cert_type: CertificateType
    cert_no: str | None = None
    issue_date: datetime.date | None = None
    electronic_status: ElectronicCertStatus
    file_material_id: str | None = None
    paper_status: PaperCertStatus
    received_date: datetime.date | None = None
    keeper: str | None = None
    location: str | None = None
    recipient: str | None = None
    recipient_date: datetime.date | None = None
    remark: str | None = None


# --------------------------------------------------------------------------
# 日期事项
# --------------------------------------------------------------------------


class DateItemIn(BaseModel):
    ip_asset_id: str | None = None
    title: str = Field(min_length=1, max_length=200)
    date_type: DateType
    planned_date: datetime.date | None = None
    due_date: datetime.date | None = None
    actual_date: datetime.date | None = None
    remind_at: datetime.datetime | None = None
    source: DateSource = DateSource.MANUAL
    rule_version: str | None = Field(default=None, max_length=64)
    needs_confirmation: bool = False
    owner_user_id: str | None = None
    remark: str | None = None


class DateItemUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    date_type: DateType | None = None
    planned_date: datetime.date | None = None
    due_date: datetime.date | None = None
    actual_date: datetime.date | None = None
    remind_at: datetime.datetime | None = None
    status: DateStatus | None = None
    owner_user_id: str | None = None
    remark: str | None = None


class DateItemOut(ORMModel):
    id: str
    ip_asset_id: str | None = None
    asset_name: str | None = None
    title: str
    date_type: DateType
    planned_date: datetime.date | None = None
    due_date: datetime.date | None = None
    actual_date: datetime.date | None = None
    remind_at: datetime.datetime | None = None
    source: DateSource
    rule_version: str | None = None
    needs_confirmation: bool
    status: DateStatus
    owner_user_id: str | None = None
    remark: str | None = None


# --------------------------------------------------------------------------
# 费用与发票
# --------------------------------------------------------------------------


class FeeIn(BaseModel):
    ip_asset_id: str | None = None
    fee_type: FeeType
    description: str | None = Field(default=None, max_length=255)
    amount_due: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    amount_paid: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    due_date: datetime.date | None = None
    paid_date: datetime.date | None = None
    coverage_end_date: datetime.date | None = None
    payee: str | None = Field(default=None, max_length=160)
    payer: str | None = Field(default=None, max_length=160)
    payment_method: str | None = Field(default=None, max_length=64)
    status: FeeStatus | None = None
    voucher_material_id: str | None = None
    handler: str | None = Field(default=None, max_length=64)
    remark: str | None = None


class FeeOut(ORMModel):
    id: str
    ip_asset_id: str | None = None
    # 列表展示用的案件信息（以名称为中心）
    asset_name: str | None = None
    docket_no: str | None = None
    application_no: str | None = None
    fee_type: FeeType
    description: str | None = None
    amount_due: Decimal
    amount_paid: Decimal | None = None
    currency: str
    due_date: datetime.date | None = None
    paid_date: datetime.date | None = None
    coverage_end_date: datetime.date | None = None
    payee: str | None = None
    payer: str | None = None
    payment_method: str | None = None
    # 该费用已关联的发票数量（发票在费用详情中查看）
    invoice_count: int = 0
    status: FeeStatus
    voucher_material_id: str | None = None
    handler: str | None = None
    remark: str | None = None


class InvoiceIn(BaseModel):
    ip_asset_id: str | None = None
    invoice_no: str = Field(min_length=1, max_length=64)
    invoice_code: str | None = Field(default=None, max_length=32)
    invoice_type: str | None = Field(default=None, max_length=32)
    issuer: str | None = Field(default=None, max_length=160)
    buyer: str | None = Field(default=None, max_length=160)
    invoice_date: datetime.date | None = None
    amount_net: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    tax_amount: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    amount_gross: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    reimbursement_status: ReimbursementStatus = ReimbursementStatus.NOT_SUBMITTED
    reimbursement_date: datetime.date | None = None
    original_status: InvoiceOriginalStatus = InvoiceOriginalStatus.IN_STORAGE
    file_material_id: str | None = None
    remark: str | None = None
    fee_ids: list[str] = []


class InvoiceOut(ORMModel):
    id: str
    ip_asset_id: str | None = None
    asset_name: str | None = None
    docket_no: str | None = None
    invoice_no: str
    invoice_code: str | None = None
    invoice_type: str | None = None
    issuer: str | None = None
    buyer: str | None = None
    invoice_date: datetime.date | None = None
    amount_net: Decimal | None = None
    tax_amount: Decimal | None = None
    amount_gross: Decimal | None = None
    currency: str
    reimbursement_status: ReimbursementStatus
    reimbursement_date: datetime.date | None = None
    original_status: InvoiceOriginalStatus
    file_material_id: str | None = None
    remark: str | None = None
    fee_ids: list[str] = []


# --------------------------------------------------------------------------
# 统计
# --------------------------------------------------------------------------


class MetricDefinition(BaseModel):
    """统计口径声明，随指标一起返回，避免口径不明。"""

    key: str
    label: str
    source: str
    filter: str
    date_field: str | None = None
    dedup: str = "按 ip_assets.id 去重"
    status_scope: str | None = None
    empty_behavior: str = "无数据时返回 0 或空列表"


class DashboardTaskOut(BaseModel):
    id: str
    ip_asset_id: str | None = None
    asset_name: str | None = None
    title: str
    date_type: DateType
    due_date: datetime.date
    days_left: int


class DashboardFeeOut(BaseModel):
    id: str
    ip_asset_id: str
    asset_name: str
    docket_no: str | None = None
    fee_type: FeeType
    amount_paid: Decimal | None = None
    amount_due: Decimal
    currency: str
    paid_date: datetime.date | None = None


class DashboardMaterialOut(BaseModel):
    id: str
    ip_asset_id: str | None = None
    asset_name: str | None = None
    display_name: str
    extraction_status: ExtractionStatus
    extraction_kind: str | None = None
    extraction_error: str | None = None
    updated_at: datetime.datetime


class DashboardRecentAssetOut(ORMModel):
    id: str
    name: str
    docket_no: str | None = None
    ip_type: IpType
    status_group: AssetStatus
    updated_at: datetime.datetime


class WorkbenchOut(BaseModel):
    total_assets: int
    in_progress_assets: int
    pending_date_count: int
    missing_invoice_fee_count: int
    extraction_attention_count: int
    tasks: list[DashboardTaskOut]
    missing_invoice_fees: list[DashboardFeeOut]
    extraction_attention: list[DashboardMaterialOut]
    recent_assets: list[DashboardRecentAssetOut]
    due_soon_days: int
    metrics: list[MetricDefinition]


class DashboardOut(BaseModel):
    total_assets: int
    by_type: dict[str, int]
    by_status: dict[str, int]
    granted_rate: float
    new_this_year: int
    certificates_by_type: dict[str, int]
    due_soon: list[DateItemOut]
    due_soon_days: int
    metrics: list[MetricDefinition]


# --------------------------------------------------------------------------
# 用户、审计与导入导出
# --------------------------------------------------------------------------


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    display_name: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.USER
    email: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=32)


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=64)
    role: UserRole | None = None
    email: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=32)
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


class AuditLogOut(ORMModel):
    id: str
    user_id: str | None = None
    action: str
    object_type: str
    object_id: str | None = None
    summary: str | None = None
    ip_address: str | None = None
    created_at: datetime.datetime


class ImportRowError(BaseModel):
    row: int
    message: str


class ImportResult(BaseModel):
    total_rows: int
    created: int
    skipped: int
    errors: list[ImportRowError]


class YearlyPoint(BaseModel):
    year: int
    count: int


class YearlyOut(BaseModel):
    """年度新增统计。

    date_field 随响应返回，明确使用的是创建时间而非申请/登记日期。
    """

    date_field: str
    ip_type: str | None = None
    items: list[YearlyPoint]
    metric: MetricDefinition

