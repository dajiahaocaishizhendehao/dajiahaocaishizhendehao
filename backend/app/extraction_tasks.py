"""材料 OCR 后台任务。

上传请求只创建材料与 pending 状态；识别在线程池中运行，任务自行创建数据库会话，
不占用原 HTTP 请求的事务与连接。失败保留原件并记录有限长度错误，可重新提交任务。
"""

from __future__ import annotations

import datetime
import threading
from concurrent.futures import ThreadPoolExecutor

from app import extraction
from app.constants import ExtractionStatus
from app.database import SessionLocal, get_engine
from app.models import Material
from app.storage import get_storage

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ipms-ocr")
_reader_gate = threading.Semaphore(1)


def submit_extraction(material_id: str, kind: str) -> None:
    _executor.submit(_run_extraction, material_id, kind)


def _run_extraction(material_id: str, kind: str) -> None:
    session = SessionLocal(bind=get_engine())
    try:
        material = session.get(Material, material_id)
        if material is None or material.is_deleted:
            return
        material.extraction_status = ExtractionStatus.RUNNING
        material.extraction_kind = kind
        material.extraction_started_at = datetime.datetime.now(datetime.timezone.utc)
        material.extraction_finished_at = None
        material.extraction_error = None
        session.commit()

        path = get_storage().root / material.storage_key
        try:
            # EasyOCR reader 暂按单并发保护；PDF 文本层解析也在同一任务入口保持行为一致。
            with _reader_gate:
                source, text, layout_words = extraction.read_document(path, material.ext)
            if not text.strip():
                raise extraction.ExtractionUnavailable("未能从文件中提取到文字")
            if kind == "invoice":
                if layout_words:
                    fields, warnings = extraction.parse_invoice_layout(layout_words)
                    # 布局解析缺失的字段再由文本解析补充，而不是覆盖更可靠的坐标结果。
                    fallback_fields, fallback_warnings = extraction.parse_invoice(text)
                    fields = {**fallback_fields, **fields}
                    if not warnings:
                        warnings = []
                    elif not fallback_warnings:
                        warnings = []
                else:
                    fields, warnings = extraction.parse_invoice(text)
            else:
                fields, warnings = extraction.parse_certificate(text)

            material = session.get(Material, material_id)
            if material is None:
                return
            material.extraction_status = ExtractionStatus.SUCCEEDED
            material.extraction_source = source
            material.extraction_fields = {"fields": fields, "warnings": warnings}
            material.extraction_text = text[:4000]
            material.extraction_error = None
        except Exception as error:  # 后台任务必须把失败落库，不能静默退出
            material = session.get(Material, material_id)
            if material is None:
                return
            material.extraction_status = ExtractionStatus.FAILED
            material.extraction_fields = None
            material.extraction_text = None
            material.extraction_error = str(error)[:500]
        material.extraction_finished_at = datetime.datetime.now(datetime.timezone.utc)
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()
