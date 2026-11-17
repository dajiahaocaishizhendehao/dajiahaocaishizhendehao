"""证书扫描件识别：PDF/图片 → 文本 → 结构化字段。

依赖（按需导入，缺失时抛 ExtractionUnavailable）：
- pymupdf：PDF 渲染与文本层提取
- easyocr：图片 OCR（中文简体 + 英文，CPU 可运行）

重要约定：识别结果只作为「建议值」返回，必须由人确认后才写入档案。
"""

from __future__ import annotations

import datetime
import pathlib
import re
from dataclasses import dataclass, field


class ExtractionUnavailable(RuntimeError):
    """运行环境缺少 OCR / PDF 依赖。"""


@dataclass
class ExtractionResult:
    source: str
    text: str
    fields: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _normalize(text: str) -> str:
    table = str.maketrans(
        {
            "：": ":",
            "（": "(",
            "）": ")",
            "，": ",",
            "；": ";",
            "　": " ",
            "\u00a0": " ",
        }
    )
    text = text.translate(table)
    text = re.sub(r"[ \t]+", " ", text)
    return text


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def read_document(path: pathlib.Path, ext: str | None) -> tuple[str, str, list[tuple]]:
    """返回 (来源, 文本, 带坐标词元)。"""

    suffix = (ext or path.suffix.lstrip(".")).lower()
    if suffix == "pdf":
        try:
            import pymupdf
        except ImportError as error:
            raise ExtractionUnavailable("未安装 pymupdf，无法解析 PDF") from error
        document = pymupdf.open(path)
        try:
            text = "".join(page.get_text() for page in document)
            words = [word for page in document for word in page.get_text("words", sort=True)]
            if len(text.strip()) >= 20:
                return "text-layout" if words else "text-layer", text, words
            if document.page_count == 0:
                return "ocr", "", []
            # 对扫描件提高到 220 DPI，并做对比度增强后交给 OCR。
            pixmap = document[0].get_pixmap(dpi=220, colorspace=pymupdf.csGRAY)
            png = path.with_suffix(".ocr.png")
            pixmap.save(png)
        finally:
            document.close()
        try:
            return "ocr", _ocr_image(png), []
        finally:
            png.unlink(missing_ok=True)
    if suffix in {"png", "jpg", "jpeg", "webp"}:
        return "ocr", _ocr_image(path), []
    raise ExtractionUnavailable(f"暂不支持识别 {suffix} 类型文件")


def read_text(path: pathlib.Path, ext: str | None) -> tuple[str, str]:
    source, text, _ = read_document(path, ext)
    return source, text


def _legacy_read_text(path: pathlib.Path, ext: str | None) -> tuple[str, str]:
    """返回 (来源, 文本)。来源为 text-layer 或 ocr。"""

    suffix = (ext or path.suffix.lstrip(".")).lower()

    if suffix == "pdf":
        try:
            import pymupdf
        except ImportError as error:  # pragma: no cover - 环境相关
            raise ExtractionUnavailable("未安装 pymupdf，无法解析 PDF") from error

        document = pymupdf.open(path)
        try:
            text = "".join(page.get_text() for page in document)
            if len(text.strip()) >= 20:
                return "text-layer", text

            # 扫描件：渲染首页后 OCR
            if document.page_count == 0:
                return "ocr", ""
            pixmap = document[0].get_pixmap(dpi=180)
            png = path.with_suffix(".ocr.png")
            pixmap.save(png)
        finally:
            document.close()

        try:
            return "ocr", _ocr_image(png)
        finally:
            png.unlink(missing_ok=True)

    if suffix in {"png", "jpg", "jpeg", "webp"}:
        return "ocr", _ocr_image(path)

    raise ExtractionUnavailable(f"暂不支持识别 {suffix} 类型文件")


_reader = None


def _ocr_image(path: pathlib.Path) -> str:
    global _reader
    try:
        import easyocr
    except ImportError as error:  # pragma: no cover - 环境相关
        raise ExtractionUnavailable("未安装 easyocr，无法识别图片文字") from error

    if _reader is None:
        # download_enabled=False：只用本机已缓存的模型，避免联网。
        # quantize=False：部分 CPU 不支持量化 LSTM 所需的 AVX2/FBGEMM 指令，
        # 开启量化会在识别阶段触发 Illegal instruction。
        _reader = easyocr.Reader(["ch_sim", "en"], gpu=False, download_enabled=False, quantize=False)
    lines = _reader.readtext(str(path), detail=0, paragraph=False)
    return "\n".join(lines)


PATTERNS: list[tuple[str, str]] = [
    # OCR 常把 CN/ZL 前缀识别成“兀、几、儿”等字符；只信任后面的长数字主体。
    ("patent_no", r"专利号[:：]?\s*[^\d\n]{0,4}(\d{8,14}(?:\.\d)?)"),
    ("certificate_no", r"证书号[:：]?\s*([0-9]{4,10})"),
    ("name", r"名\s*称[:：]\s*([^\n]{2,80})"),
    ("patentee", r"专利权人[:：]\s*([^\n]{2,60})"),
    ("inventors", r"发?明\s*人[:：]\s*([^\n]{2,120})"),
    ("legal_status", r"法律状态[:：]?\s*([^\n]{2,40})"),
    ("address", r"专利权人地址[:：]\s*([^\n]{4,120})"),
]


def _clean_patent_no(value: str) -> str:
    text = _compact(value).upper()
    text = re.sub(r"^[A-Z]{0,2}", "", text)
    return text


def _find_date(text: str, keyword: str) -> str | None:
    """在关键字附近找 20xx年x月x日。"""

    index = text.find(keyword)
    scope = text[index : index + 60] if index >= 0 else text
    match = re.search(r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", scope)
    if not match:
        return None
    try:
        return datetime.date(int(match.group(1)), int(match.group(2)), int(match.group(3))).isoformat()
    except ValueError:
        return None


def parse_certificate(text: str) -> tuple[dict[str, str], list[str]]:
    normalized = _normalize(text)
    fields: dict[str, str] = {}
    warnings: list[str] = []

    for key, pattern in PATTERNS:
        match = re.search(pattern, normalized)
        if match:
            value = match.group(1).strip(" :：")
            if key == "patent_no":
                value = _clean_patent_no(value)
            if value:
                fields[key] = value

    # 有些扫描件把真正的“名称:”标签漏识别，而后文“原专利权人名称”会误命中通用正则。
    # 因此只要能从“著录项目”后的首个日期之前取得中文长行，就优先采用该版面位置的名称。
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    start = next((index for index, line in enumerate(lines) if "著录项目" in line), -1)
    if start >= 0:
        for line in lines[start + 1 : start + 8]:
            if re.search(r"20\d{2}年", line):
                break
            if len(line) >= 6 and re.search(r"[\u4e00-\u9fff]{4,}", line) and not any(
                word in line for word in ("分类", "发明人", "专利权人", "申请人", "原专利权人")
            ):
                fields["name"] = line
                break

    application_date = _find_date(normalized, "申请日")
    if not application_date:
        # 登记簿 OCR 可能漏掉“申请日”标签；著录项目中的第一个完整日期通常为申请日。
        marker = normalized.find("著录项目")
        scope = normalized[marker : marker + 500] if marker >= 0 else ""
        date_match = re.search(r"(20\d{2})年(\d{1,2})月(\d{1,2})日", scope)
        if date_match:
            try:
                application_date = datetime.date(*map(int, date_match.groups())).isoformat()
            except ValueError:
                application_date = None
    if application_date:
        fields["application_date"] = application_date

    grant_date = _find_date(normalized, "授权公告日") or _find_date(normalized, "授权日")
    if grant_date:
        fields["grant_date"] = grant_date

    if "inventors" in fields:
        fields["inventors"] = re.sub(r"[。、,，;；]", "、", fields["inventors"]).strip("、")

    if not fields.get("patent_no") and not fields.get("application_no"):
        warnings.append("未识别到专利号/申请号，请人工核对")
    if not fields.get("name"):
        warnings.append("未识别到名称，请人工核对")

    return fields, warnings


def extract(path: pathlib.Path, ext: str | None) -> ExtractionResult:
    source, text = read_text(path, ext)
    if not text.strip():
        raise ExtractionUnavailable("未能从文件中提取到文字")
    fields, warnings = parse_certificate(text)
    return ExtractionResult(source=source, text=text, fields=fields, warnings=warnings)


# --------------------------------------------------------------------------
# 增值税发票解析
# --------------------------------------------------------------------------

MONEY = r"[¥￥]?\s*([0-9][0-9,]*\.\d{2})"


def _money(value: str | None) -> str | None:
    if not value:
        return None
    return value.replace(",", "")


def parse_invoice_layout(words: list[tuple]) -> tuple[dict[str, str], list[str]]:
    """按 PDF 文本坐标解析电子发票。

    国家税务电子发票常把标签与值拆成不同文本块，普通换行正则无法命中；
    此解析器利用同一水平行和固定区域识别号码、日期、购销方与合计金额。
    """

    tokens = [
        {"x0": float(item[0]), "y0": float(item[1]), "x1": float(item[2]), "y1": float(item[3]), "text": str(item[4]).strip()}
        for item in words
        if len(item) >= 5 and str(item[4]).strip()
    ]
    fields: dict[str, str] = {}
    warnings: list[str] = []

    def same_line_after(label: str, *, tolerance: float = 5.0) -> str | None:
        marker = next((item for item in tokens if label in item["text"]), None)
        if marker is None:
            return None
        candidates = [
            item for item in tokens
            if item["x0"] >= marker["x1"] - 2 and abs(item["y0"] - marker["y0"]) <= tolerance
        ]
        candidates.sort(key=lambda item: item["x0"])
        return candidates[0]["text"] if candidates else None

    invoice_no = same_line_after("发票号码")
    if invoice_no:
        match = re.search(r"\d{8,20}", invoice_no)
        if match:
            fields["invoice_no"] = match.group(0)

    invoice_date = same_line_after("开票日期")
    if invoice_date:
        match = re.search(r"(20\d{2})年(\d{1,2})月(\d{1,2})日", invoice_date)
        if match:
            try:
                fields["invoice_date"] = datetime.date(*map(int, match.groups())).isoformat()
            except ValueError:
                warnings.append("开票日期格式异常，请人工核对")

    # 左半区为购买方，右半区为销售方；严格限制候选值所在半区，排除另一个“名称”标签。
    name_markers = [
        item for item in tokens if item["text"].replace(" ", "") in {"名称:", "名称："}
    ]
    for marker in name_markers:
        is_buyer = marker["x0"] < 280
        # 字体包围盒常与下一文本块重叠 2-4px，保留少量容差。
        min_x = marker["x1"] - 5
        max_x = 295 if is_buyer else float("inf")
        candidates = [
            item
            for item in tokens
            if min_x <= item["x0"] < max_x
            and abs(item["y0"] - marker["y0"]) <= 5
            and "名称" not in item["text"]
            and item["text"] not in {"购", "买", "方", "信", "息", "销", "售"}
        ]
        candidates.sort(key=lambda item: item["x0"])
        if not candidates:
            continue
        fields["buyer" if is_buyer else "seller"] = candidates[0]["text"]

    # 价税合计小写位于页面下半部右侧，合计金额/税额位于其上一行。
    gross_candidates = []
    for item in tokens:
        if item["y0"] >= 250 and item["x0"] >= 400:
            match = re.search(r"[¥￥]?\s*([0-9][0-9,]*\.\d{2})", item["text"])
            if match:
                gross_candidates.append((item["y0"], item["x0"], match.group(1).replace(",", "")))
    if gross_candidates:
        # 最接近“（小写）”区域且位于较低行的金额是价税合计。
        gross_candidates.sort(key=lambda item: (item[0], item[1]))
        fields["amount_gross"] = gross_candidates[-1][2]

    total_values: list[tuple[float, str]] = []
    for item in tokens:
        if 245 <= item["y0"] <= 272 and item["x0"] >= 360:
            match = re.search(r"[¥￥]?\s*([0-9][0-9,]*\.\d{2})", item["text"])
            if match:
                total_values.append((item["x0"], match.group(1).replace(",", "")))
    total_values.sort(key=lambda item: item[0])
    if total_values:
        fields["amount_net"] = total_values[0][1]
    if len(total_values) > 1:
        fields["tax_amount"] = total_values[-1][1]

    if "invoice_no" not in fields:
        warnings.append("未识别到发票号码，请人工填写")
    if "amount_gross" not in fields:
        warnings.append("未识别到价税合计，请人工填写")
    return fields, warnings


def parse_invoice(text: str) -> tuple[dict[str, str], list[str]]:
    """从发票 OCR 文本中提取号码、日期、金额与购销方。

    金额只做格式规整，不做勾稽校验；是否与费用对应由人工确认。
    """

    normalized = _normalize(text)
    fields: dict[str, str] = {}
    warnings: list[str] = []

    number = re.search(r"发票号码[:：]?\s*(\d{8,20})", normalized)
    if number:
        fields["invoice_no"] = number.group(1)

    code = re.search(r"发票代码[:：]?\s*(\d{10,12})", normalized)
    if code:
        fields["invoice_code"] = code.group(1)

    date = re.search(r"开票日期[:：]?\s*(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", normalized)
    if date:
        try:
            fields["invoice_date"] = datetime.date(
                int(date.group(1)), int(date.group(2)), int(date.group(3))
            ).isoformat()
        except ValueError:
            warnings.append("开票日期格式异常，请人工核对")

    gross = re.search(r"价税合计.{0,20}?" + MONEY, normalized, flags=re.S)
    if gross:
        fields["amount_gross"] = _money(gross.group(1)) or ""

    # 「合 计」行通常包含两个金额：金额、税额。优先按该行解析，避免命中表头。
    total_line = re.search(r"合\s*计[^\n]{0,60}", normalized)
    if total_line:
        amounts = re.findall(r"([0-9][0-9,]*\.\d{2})", total_line.group(0))
        if amounts:
            fields["amount_net"] = amounts[0].replace(",", "")
        if len(amounts) > 1:
            fields["tax_amount"] = amounts[1].replace(",", "")

    if "tax_amount" not in fields:
        tax = re.search(r"税\s*额[^\n]{0,12}?[¥￥]\s*([0-9][0-9,]*\.\d{2})", normalized)
        if tax:
            fields["tax_amount"] = tax.group(1).replace(",", "")

    parties = re.findall(r"名\s*称[:：]\s*([^\n]{2,40})", normalized)
    if parties:
        fields["buyer"] = parties[0].strip()
        if len(parties) > 1:
            fields["seller"] = parties[1].strip()

    invoice_signals = sum(
        marker in normalized
        for marker in ("发票号码", "开票日期", "价税合计", "购买方", "销售方", "纳税人识别号")
    )
    if invoice_signals < 2:
        warnings.append("文件内容疑似不是发票，请确认上传文件")
    else:
        if "invoice_no" not in fields:
            # 文本层常把标签和值拆开；从全文找 18-20 位号码作为保守兜底。
            candidates = re.findall(r"(?<!\d)(\d{18,20})(?!\d)", normalized)
            if candidates:
                fields["invoice_no"] = candidates[0]
            else:
                warnings.append("未识别到发票号码，请人工填写")
        if "amount_gross" not in fields:
            gross_values = re.findall(r"[¥￥]\s*([0-9][0-9,]*\.\d{2})", normalized)
            if gross_values:
                fields["amount_gross"] = gross_values[-1].replace(",", "")
            else:
                warnings.append("未识别到价税合计，请人工填写")

    return fields, warnings

