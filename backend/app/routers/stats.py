"""统计接口。

每个指标同时返回口径说明（来源、过滤条件、日期字段、去重规则、空数据处理），
避免前端展示无法追溯的数字。
"""

from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_user
from app.domain import granted_rate, group_counts_by_year
from app.models import (
    AssetStatus,
    Certificate,
    CertificateType,
    DateItem,
    DateStatus,
    ExtractionStatus,
    Fee,
    FeeStatus,
    Invoice,
    InvoiceFee,
    IpAsset,
    IpType,
    Material,
    User,
)
from app.schemas import (
    DashboardFeeOut,
    DashboardMaterialOut,
    DashboardOut,
    DashboardRecentAssetOut,
    DashboardTaskOut,
    DateItemOut,
    MetricDefinition,
    WorkbenchOut,
    YearlyOut,
    YearlyPoint,
)
from app.services import scoped_assets, scoped_related

router = APIRouter(prefix="/stats", tags=["统计"])

METRICS: list[MetricDefinition] = [
    MetricDefinition(
        key="total_assets",
        label="知识产权总数",
        source="ip_assets",
        filter="is_deleted = false，并应用当前用户数据范围",
        dedup="按 ip_assets.id 去重",
        status_scope="全部状态",
        empty_behavior="无数据时返回 0",
    ),
    MetricDefinition(
        key="by_type",
        label="按类型分布",
        source="ip_assets.ip_type",
        filter="is_deleted = false",
        dedup="按 ip_assets.id 去重",
        status_scope="全部状态",
        empty_behavior="无数据时返回空对象",
    ),
    MetricDefinition(
        key="by_status",
        label="按综合状态分布",
        source="ip_assets.status_group",
        filter="is_deleted = false",
        dedup="按 ip_assets.id 去重",
        status_scope="in_progress / granted / invalid / other",
        empty_behavior="无数据时返回空对象",
    ),
    MetricDefinition(
        key="new_this_year",
        label="本年度新增",
        source="ip_assets.created_at",
        filter="created_at 落在本自然年（服务器时区 UTC）",
        date_field="created_at",
        dedup="按 ip_assets.id 去重",
        status_scope="全部状态",
        empty_behavior="无数据时返回 0",
    ),
    MetricDefinition(
        key="granted_rate",
        label="已取得权利占比",
        source="ip_assets.status_group",
        filter="status_group = granted 的档案数 / 同范围档案总数",
        dedup="按 ip_assets.id 去重",
        status_scope="granted",
        empty_behavior="总数为 0 时返回 0.0，不返回 NaN",
    ),
    MetricDefinition(
        key="certificates_by_type",
        label="证书数量（按类型）",
        source="certificates.cert_type",
        filter="is_deleted = false",
        dedup="按 certificates.id 去重",
        status_scope="全部状态",
        empty_behavior="无数据时返回空对象",
    ),
    MetricDefinition(
        key="due_soon",
        label="即将到期事项",
        source="date_items",
        filter="status = open 且 due_date 在窗口内",
        date_field="due_date",
        dedup="按 date_items.id 去重",
        status_scope="仅未完成事项",
        empty_behavior="无数据时返回空列表",
    ),
]


WORKBENCH_METRICS: list[MetricDefinition] = [
    MetricDefinition(
        key="pending_date_count",
        label="待处理日期",
        source="date_items",
        filter="is_deleted=false、status=open、已逾期或未来窗口内，并应用当前用户数据范围",
        date_field="due_date",
        dedup="按 date_items.id 去重",
        status_scope="open",
        empty_behavior="无数据时返回 0 和空列表",
    ),
    MetricDefinition(
        key="missing_invoice_fee_count",
        label="缺少发票费用",
        source="fees + invoice_fees + invoices",
        filter="费用未删除、已支付或部分支付、未关联有效发票，并应用当前用户数据范围",
        date_field="paid_date",
        dedup="按 fees.id 去重",
        status_scope="paid / partial",
        empty_behavior="无数据时返回 0 和空列表",
    ),
    MetricDefinition(
        key="extraction_attention_count",
        label="识别待处理",
        source="materials",
        filter="材料未删除、识别状态为 pending/running/failed，并应用当前用户数据范围",
        date_field="updated_at",
        dedup="按 materials.id 去重",
        status_scope="pending / running / failed",
        empty_behavior="无数据时返回 0 和空列表",
    ),
    MetricDefinition(
        key="recent_assets",
        label="最近更新案件",
        source="ip_assets",
        filter="is_deleted=false，并应用当前用户数据范围",
        date_field="updated_at",
        dedup="按 ip_assets.id 去重",
        status_scope="全部状态",
        empty_behavior="无数据时返回空列表",
    ),
]


@router.get("/workbench", response_model=WorkbenchOut)
def workbench(
    due_soon_days: int | None = Query(default=None, ge=1, le=365),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> WorkbenchOut:
    """以日常处理为中心的工作台聚合接口。"""

    settings = get_settings()
    window = due_soon_days or settings.due_soon_days
    today = datetime.datetime.now(datetime.timezone.utc).date()
    visible_asset_ids = scoped_assets(
        select(IpAsset.id).where(IpAsset.is_deleted.is_(False)), user
    )

    total_assets = db.scalar(select(func.count()).select_from(visible_asset_ids.subquery())) or 0
    in_progress_assets = db.scalar(
        select(func.count(IpAsset.id)).where(
            IpAsset.id.in_(visible_asset_ids), IpAsset.status_group == AssetStatus.IN_PROGRESS
        )
    ) or 0

    task_stmt = (
        select(DateItem, IpAsset.name)
        .outerjoin(IpAsset, IpAsset.id == DateItem.ip_asset_id)
        .where(
            DateItem.is_deleted.is_(False),
            DateItem.status == DateStatus.OPEN,
            DateItem.due_date.is_not(None),
            DateItem.due_date <= today + datetime.timedelta(days=window),
            DateItem.ip_asset_id.in_(visible_asset_ids),
        )
        .order_by(DateItem.due_date.asc())
    )
    task_rows = db.execute(task_stmt.limit(10)).all()
    pending_date_count = db.scalar(select(func.count()).select_from(task_stmt.order_by(None).subquery())) or 0
    tasks = [
        DashboardTaskOut(
            id=item.id,
            ip_asset_id=item.ip_asset_id,
            asset_name=asset_name,
            title=item.title,
            date_type=item.date_type,
            due_date=item.due_date,
            days_left=(item.due_date - today).days,
        )
        for item, asset_name in task_rows
    ]

    valid_invoice_exists = exists(
        select(InvoiceFee.id)
        .join(Invoice, Invoice.id == InvoiceFee.invoice_id)
        .where(InvoiceFee.fee_id == Fee.id, Invoice.is_deleted.is_(False))
    )
    missing_fee_stmt = (
        select(Fee, IpAsset.name, IpAsset.docket_no)
        .join(IpAsset, IpAsset.id == Fee.ip_asset_id)
        .where(
            Fee.is_deleted.is_(False),
            Fee.ip_asset_id.in_(visible_asset_ids),
            Fee.status.in_([FeeStatus.PAID, FeeStatus.PARTIAL]),
            ~valid_invoice_exists,
        )
        .order_by(Fee.paid_date.desc().nulls_last(), Fee.updated_at.desc())
    )
    missing_invoice_fee_count = db.scalar(
        select(func.count()).select_from(missing_fee_stmt.order_by(None).subquery())
    ) or 0
    missing_invoice_fees = [
        DashboardFeeOut(
            id=fee.id,
            ip_asset_id=fee.ip_asset_id,
            asset_name=asset_name,
            docket_no=docket_no,
            fee_type=fee.fee_type,
            amount_paid=fee.amount_paid,
            amount_due=fee.amount_due,
            currency=fee.currency,
            paid_date=fee.paid_date,
        )
        for fee, asset_name, docket_no in db.execute(missing_fee_stmt.limit(6)).all()
    ]

    attention_statuses = [ExtractionStatus.PENDING, ExtractionStatus.RUNNING, ExtractionStatus.FAILED]
    material_stmt = (
        select(Material, IpAsset.name)
        .outerjoin(IpAsset, IpAsset.id == Material.ip_asset_id)
        .where(
            Material.is_deleted.is_(False),
            Material.ip_asset_id.in_(visible_asset_ids),
            Material.extraction_status.in_(attention_statuses),
        )
        .order_by(Material.updated_at.desc())
    )
    extraction_attention_count = db.scalar(
        select(func.count()).select_from(material_stmt.order_by(None).subquery())
    ) or 0
    extraction_attention = [
        DashboardMaterialOut(
            id=material.id,
            ip_asset_id=material.ip_asset_id,
            asset_name=asset_name,
            display_name=material.display_name,
            extraction_status=material.extraction_status,
            extraction_kind=material.extraction_kind,
            extraction_error=material.extraction_error,
            updated_at=material.updated_at,
        )
        for material, asset_name in db.execute(material_stmt.limit(6)).all()
    ]

    recent_rows = db.scalars(
        scoped_assets(
            select(IpAsset).where(IpAsset.is_deleted.is_(False)).order_by(IpAsset.updated_at.desc()), user
        ).limit(6)
    ).all()
    recent_assets = [DashboardRecentAssetOut.model_validate(item) for item in recent_rows]

    return WorkbenchOut(
        total_assets=int(total_assets),
        in_progress_assets=int(in_progress_assets),
        pending_date_count=int(pending_date_count),
        missing_invoice_fee_count=int(missing_invoice_fee_count),
        extraction_attention_count=int(extraction_attention_count),
        tasks=tasks,
        missing_invoice_fees=missing_invoice_fees,
        extraction_attention=extraction_attention,
        recent_assets=recent_assets,
        due_soon_days=window,
        metrics=WORKBENCH_METRICS,
    )


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(
    due_soon_days: int | None = Query(default=None, ge=1, le=365),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DashboardOut:
    settings = get_settings()
    window = due_soon_days or settings.due_soon_days
    today = datetime.datetime.now(datetime.timezone.utc).date()

    base = scoped_assets(select(IpAsset).where(IpAsset.is_deleted.is_(False)), user)
    total_assets = db.scalar(select(func.count()).select_from(base.subquery())) or 0

    type_rows = db.execute(
        scoped_assets(
            select(IpAsset.ip_type, func.count(IpAsset.id))
            .where(IpAsset.is_deleted.is_(False))
            .group_by(IpAsset.ip_type),
            user,
        )
    ).all()
    by_type = {row[0].value: int(row[1]) for row in type_rows}

    status_rows = db.execute(
        scoped_assets(
            select(IpAsset.status_group, func.count(IpAsset.id))
            .where(IpAsset.is_deleted.is_(False))
            .group_by(IpAsset.status_group),
            user,
        )
    ).all()
    by_status = {row[0].value: int(row[1]) for row in status_rows}

    year_start = datetime.datetime(today.year, 1, 1, tzinfo=datetime.timezone.utc)
    year_end = datetime.datetime(today.year + 1, 1, 1, tzinfo=datetime.timezone.utc)
    new_this_year_stmt = scoped_assets(
        select(func.count(IpAsset.id)).where(
            IpAsset.is_deleted.is_(False),
            IpAsset.created_at >= year_start,
            IpAsset.created_at < year_end,
        ),
        user,
    )
    new_this_year = db.scalar(new_this_year_stmt) or 0

    cert_stmt = scoped_related(
        select(Certificate.cert_type, func.count(Certificate.id))
        .where(Certificate.is_deleted.is_(False))
        .group_by(Certificate.cert_type),
        Certificate.ip_asset_id,
        user,
    )
    cert_rows = db.execute(cert_stmt).all()
    certificates_by_type = {row[0].value: int(row[1]) for row in cert_rows}

    due_stmt = scoped_related(
        select(DateItem)
        .where(
            DateItem.is_deleted.is_(False),
            DateItem.status == DateStatus.OPEN,
            DateItem.due_date.is_not(None),
            DateItem.due_date >= today,
            DateItem.due_date <= today + datetime.timedelta(days=window),
        )
        .order_by(DateItem.due_date.asc())
        .limit(20),
        DateItem.ip_asset_id,
        user,
    )
    due_items = [DateItemOut.model_validate(row) for row in db.scalars(due_stmt).all()]

    return DashboardOut(
        total_assets=int(total_assets),
        by_type=by_type,
        by_status=by_status,
        granted_rate=granted_rate(by_status, int(total_assets)),
        new_this_year=int(new_this_year),
        certificates_by_type=certificates_by_type,
        due_soon=due_items,
        due_soon_days=window,
        metrics=METRICS,
    )


@router.get("/yearly", response_model=YearlyOut)
def yearly(
    ip_type: IpType | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> YearlyOut:
    """按创建年份汇总档案数量。

    明确使用 created_at（入库时间），不是申请日或登记日；
    正式统计口径确认后可改为按业务日期统计。
    """

    stmt = scoped_assets(select(IpAsset.created_at).where(IpAsset.is_deleted.is_(False)), user)
    if ip_type:
        stmt = stmt.where(IpAsset.ip_type == ip_type)
    rows = [value for value in db.scalars(stmt).all() if value is not None]

    counts = group_counts_by_year(list(rows))
    metric = MetricDefinition(
        key="yearly_new",
        label="年度新增",
        source="ip_assets.created_at",
        filter="is_deleted = false" + (f" 且 ip_type = {ip_type.value}" if ip_type else ""),
        date_field="created_at",
        dedup="按 ip_assets.id 去重",
        status_scope="全部状态",
        empty_behavior="无数据时返回空列表",
    )
    return YearlyOut(
        date_field="created_at",
        ip_type=ip_type.value if ip_type else None,
        items=[YearlyPoint(year=year, count=count) for year, count in counts.items()],
        metric=metric,
    )


__all__ = ["router", "METRICS", "IpType", "AssetStatus", "CertificateType"]
