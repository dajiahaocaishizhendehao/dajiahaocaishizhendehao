"""纯业务规则（不依赖 FastAPI、SQLAlchemy 与数据库）。

放在这里的目的：让关键规则可以脱离运行环境做单元测试，
并且让接口层只负责协议转换与持久化。
"""

from __future__ import annotations

import datetime
import io
import zipfile
from decimal import Decimal, InvalidOperation

from app.constants import AssetStatus, FeeStatus, IpType

# --------------------------------------------------------------------------
# 档案类型与专业字段
# --------------------------------------------------------------------------


class DomainError(ValueError):
    """可预期的业务校验失败。"""


def validate_type_payload(
    ip_type: IpType,
    patent: object | None,
    copyright_: object | None,
    trademark: object | None,
) -> None:
    """同一档案只能提交与自身类型匹配的专业字段。"""

    provided = {
        IpType.PATENT: patent is not None,
        IpType.COPYRIGHT: copyright_ is not None,
        IpType.TRADEMARK: trademark is not None,
    }
    for key, has_payload in provided.items():
        if key is not ip_type and has_payload:
            raise DomainError(f"{key.value} 类型不能提交其他类型的专业字段")


# --------------------------------------------------------------------------
# 费用金额
# --------------------------------------------------------------------------


def derive_fee_status(
    amount_due: Decimal,
    amount_paid: Decimal | None,
    explicit: FeeStatus | None = None,
) -> FeeStatus:
    """根据应付与实付金额推导支付状态。

    显式传入的状态优先；金额相等视为已支付，部分支付为 partial。
    不在此处推算发票金额，避免三种金额混用。
    """

    if amount_due < 0:
        raise DomainError("应付金额不能为负数")
    if amount_paid is not None and amount_paid < 0:
        raise DomainError("实付金额不能为负数")
    if explicit == FeeStatus.CANCELED:
        return explicit
    if amount_paid is None or amount_paid == 0:
        derived = FeeStatus.UNPAID
    elif amount_paid >= amount_due:
        derived = FeeStatus.PAID
    else:
        derived = FeeStatus.PARTIAL
    if explicit is not None and explicit != derived:
        raise DomainError(f"费用状态 {explicit.value} 与实付金额不一致，应为 {derived.value}")
    return derived


# --------------------------------------------------------------------------
# 日期规则
# --------------------------------------------------------------------------


def ensure_date_order(earlier: datetime.date | None, later: datetime.date | None, message: str) -> None:
    """后者不得早于前者；任一为空时不做校验。"""

    if earlier is not None and later is not None and later < earlier:
        raise DomainError(message)


def due_soon_window(
    today: datetime.date,
    due_date: datetime.date | None,
    window_days: int,
) -> bool:
    """判断某个截止日期是否落在“即将到期”窗口内（含端点，仅未来）。"""

    if due_date is None:
        return False
    if window_days < 1:
        raise DomainError("统计窗口必须大于 0 天")
    return today <= due_date <= today + datetime.timedelta(days=window_days)


def validate_certificate_dates(
    received_date: datetime.date | None,
    recipient_date: datetime.date | None,
) -> None:
    ensure_date_order(received_date, recipient_date, "领取日期不能早于收到日期")


# --------------------------------------------------------------------------
# 统计口径（纯计算，便于离线验证）
# --------------------------------------------------------------------------


def group_counts_by_year(dates: list[datetime.date | None]) -> dict[int, int]:
    """按年份汇总数量，忽略空值；结果按年份升序。

    用于“年度新增”类图表：调用方必须说明使用的是哪个日期字段。
    """

    counts: dict[int, int] = {}
    for value in dates:
        if value is None:
            continue
        counts[value.year] = counts.get(value.year, 0) + 1
    return dict(sorted(counts.items()))


def percentage(part: int, total: int) -> float:
    """返回百分比，保留一位小数；分母为 0 时返回 0.0，不返回 NaN。"""

    if total <= 0:
        return 0.0
    if part < 0:
        raise DomainError("子项数量不能为负数")
    return round(part * 100.0 / total, 1)


def granted_rate(by_status: dict[str, int], total: int) -> float:
    """已取得权利占比。

    口径：status_group = granted 的档案数 / 同一筛选范围内的档案总数。
    只做比例计算，不代表法律状态评价。
    """

    return percentage(int(by_status.get(AssetStatus.GRANTED.value, 0)), total)


# --------------------------------------------------------------------------
# 文件上传规则（对应 AGENTS.md 第 7 节）
# --------------------------------------------------------------------------

ALLOWED_UPLOAD_SUFFIXES: frozenset[str] = frozenset(
    {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".doc", ".docx", ".xls", ".xlsx", ".zip"}
)


def validate_file_signature(content: bytes, suffix: str) -> None:
    """验证常用上传类型的文件签名和最小容器结构。"""

    if suffix == ".pdf":
        if not content.startswith(b"%PDF-"):
            raise DomainError("文件内容不是有效的 PDF")
        return
    if suffix == ".png":
        if not content.startswith(b"\x89PNG\r\n\x1a\n"):
            raise DomainError("文件内容不是有效的 PNG 图片")
        return
    if suffix in {".jpg", ".jpeg"}:
        if not content.startswith(b"\xff\xd8\xff"):
            raise DomainError("文件内容不是有效的 JPEG 图片")
        return
    if suffix == ".webp":
        if len(content) < 12 or content[:4] != b"RIFF" or content[8:12] != b"WEBP":
            raise DomainError("文件内容不是有效的 WebP 图片")
        return
    if suffix in {".doc", ".xls"}:
        if not content.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
            raise DomainError("文件内容不是有效的 Office 二进制文档")
        return
    if suffix in {".docx", ".xlsx", ".zip"}:
        if not content.startswith(b"PK"):
            raise DomainError("文件内容不是有效的 ZIP/Office 文档")
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                names = set(archive.namelist())
                if suffix == ".docx" and "word/document.xml" not in names:
                    raise DomainError("文件内容不是有效的 DOCX 文档")
                if suffix == ".xlsx" and "xl/workbook.xml" not in names:
                    raise DomainError("文件内容不是有效的 XLSX 工作簿")
        except zipfile.BadZipFile:
            raise DomainError("文件内容不是有效的 ZIP/Office 文档") from None


def validate_upload(
    filename: str,
    content_type: str | None,
    size_bytes: int,
    *,
    content: bytes | None = None,
    allowed_suffixes: frozenset[str] = ALLOWED_UPLOAD_SUFFIXES,
    allowed_mimes: tuple[str, ...] | None = None,
    max_bytes: int,
) -> str:
    """校验上传文件并返回规范化的扩展名（含点号，小写）。

    规则：
    - 必须有文件名与受支持的扩展名，不只看 MIME；
    - 已知 MIME 时必须在白名单内；
    - 大小必须在 (0, max_bytes] 区间。
    """

    name = (filename or "").strip()
    if not name:
        raise DomainError("缺少文件名")
    if "." not in name:
        raise DomainError("文件缺少扩展名")

    suffix = "." + name.rsplit(".", 1)[1].strip().lower()
    if suffix not in allowed_suffixes:
        raise DomainError(f"不支持的文件类型：{suffix}")

    if content_type and allowed_mimes is not None and content_type not in allowed_mimes:
        raise DomainError(f"不支持的 MIME 类型：{content_type}")

    if max_bytes <= 0:
        raise DomainError("文件大小上限配置无效")
    if size_bytes <= 0:
        raise DomainError("文件内容为空")
    if size_bytes > max_bytes:
        raise DomainError(f"文件超过大小限制（上限 {max_bytes} 字节）")
    if content is not None:
        validate_file_signature(content, suffix)

    return suffix


# --------------------------------------------------------------------------
# CSV / XLSX 导入行解析
# --------------------------------------------------------------------------

# 工作台导入模板列。只有「案件名称」必填，其余列均可留空。
IMPORT_COLUMNS = (
    "我方文号",
    "申请号",
    "案件名称",
    "专利所有权人",
    "官费应缴纳日",
    "本次官费缴纳至",
    "本次官费缴纳金额",
    "缴纳日期",
)
IMPORT_REQUIRED_COLUMNS = ("案件名称",)
# 兼容 D-011 旧模板的英文 name 列。
IMPORT_NAME_COLUMNS = ("案件名称", "name")

_IMPORT_DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y年%m月%d日")


def missing_import_columns(fieldnames: list[str]) -> list[str]:
    """返回缺失的必需列；兼容旧模板的英文 name 列。"""

    if any(column in fieldnames for column in IMPORT_NAME_COLUMNS):
        return []
    return list(IMPORT_REQUIRED_COLUMNS)


def _import_value(row: dict[str, str], *keys: str) -> str:
    """按列名优先级读取第一个非空单元格，兼容中英文模板。"""

    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def parse_import_date(raw: str | None, field: str) -> datetime.date | None:
    """解析导入日期；空值返回 None，非法值抛出 DomainError。"""

    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    # Excel 日期单元格经 str() 后可能带 " 00:00:00"；兼容 ISO 的 T 分隔。
    text = text.replace("T", " ").split(" ", 1)[0]
    for fmt in _IMPORT_DATE_FORMATS:
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise DomainError(f"{field} 不是合法日期：{raw}（请使用 YYYY-MM-DD）")


def parse_import_row(row: dict[str, str]) -> dict[str, object]:
    """把一行导入数据规范化为档案字段；失败抛出 DomainError。

    模板只有「案件名称」必填；申请号、专利所有权人和官费信息均可选。
    同时兼容旧模板的 name/ip_type/status_group 列名。
    只做格式与枚举校验；其他依赖数据库的检查仍由调用方完成。
    """

    name = _import_value(row, "案件名称", "name")
    docket_no = _import_value(row, "我方文号", "docket_no")
    application_no = _import_value(row, "申请号", "application_no")
    patentee = _import_value(row, "专利所有权人", "patentee")
    # ASSUMPTION: 新模板未提供类型列，默认按专利导入；旧模板仍可通过 ip_type 指定类型。
    ip_type_raw = _import_value(row, "ip_type", "知识产权类型") or IpType.PATENT.value
    status_raw = _import_value(row, "status_group", "综合状态") or AssetStatus.IN_PROGRESS.value

    if not name:
        raise DomainError("缺少必填字段：案件名称")
    if len(name) > 255:
        raise DomainError("案件名称超过 255 个字符")
    if len(docket_no) > 64:
        raise DomainError("我方文号超过 64 个字符")
    if len(application_no) > 64:
        raise DomainError("申请号超过 64 个字符")
    if len(patentee) > 200:
        raise DomainError("专利所有权人超过 200 个字符")

    try:
        ip_type = IpType(ip_type_raw)
    except ValueError:
        raise DomainError(f"未知类型：{ip_type_raw}") from None

    try:
        status_group = AssetStatus(status_raw)
    except ValueError:
        raise DomainError(f"未知状态：{status_raw}") from None

    fee_amount = parse_decimal(
        _import_value(row, "本次官费缴纳金额", "fee_amount"), "本次官费缴纳金额"
    )
    fee_due_date = parse_import_date(
        _import_value(row, "官费应缴纳日", "fee_due_date"), "官费应缴纳日"
    )
    fee_coverage_end_date = parse_import_date(
        _import_value(row, "本次官费缴纳至", "fee_coverage_end_date"), "本次官费缴纳至"
    )
    fee_paid_date = parse_import_date(
        _import_value(row, "缴纳日期", "fee_paid_date"), "缴纳日期"
    )

    return {
        "name": name,
        "docket_no": docket_no or None,
        "ip_type": ip_type.value,
        "status_group": status_group.value,
        "application_no": application_no or None,
        "patentee": patentee or None,
        "fee_amount": fee_amount,
        "fee_due_date": fee_due_date,
        "fee_coverage_end_date": fee_coverage_end_date,
        "fee_paid_date": fee_paid_date,
    }


def parse_import_rows(
    rows: list[dict[str, str]],
    *,
    first_data_row: int = 2,
) -> tuple[list[dict[str, object]], list[tuple[int, str]]]:
    """批量解析导入行，返回 (可用行, [(行号, 错误信息)])。

    职责：逐行格式校验。依赖数据库的业务检查由调用方在持久化前完成。
    """

    accepted: list[dict[str, object]] = []
    errors: list[tuple[int, str]] = []

    for offset, row in enumerate(rows):
        row_number = first_data_row + offset
        try:
            parsed = parse_import_row(row)
        except DomainError as error:
            errors.append((row_number, str(error)))
            continue

        parsed["_row_number"] = row_number
        accepted.append(parsed)

    return accepted, errors


def parse_decimal(raw: str | None, field: str) -> Decimal | None:
    """解析金额字符串；空值返回 None，非法值抛出 DomainError。"""

    if raw is None:
        return None
    text = raw.strip().replace(",", "")
    if not text:
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise DomainError(f"{field} 不是合法金额：{raw}") from None
    if value < 0:
        raise DomainError(f"{field} 不能为负数")
    if value.as_tuple().exponent < -2:
        raise DomainError(f"{field} 最多保留两位小数")
    return value
