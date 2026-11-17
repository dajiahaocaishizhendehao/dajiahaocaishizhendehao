"""数据一致性、逻辑删除唯一约束、附件引用与文件签名测试。"""

from __future__ import annotations

import io
import unittest
from types import SimpleNamespace

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.domain import DomainError, validate_upload
from app.routers.materials import ensure_recognizable


class FileSignatureTest(unittest.TestCase):
    def test_reject_fake_pdf(self) -> None:
        with self.assertRaises(DomainError):
            validate_upload(
                "fake.pdf",
                "application/pdf",
                8,
                content=b"not-pdf!",
                allowed_mimes=("application/pdf",),
                max_bytes=1024,
            )

    def test_accept_pdf_signature(self) -> None:
        suffix = validate_upload(
            "ok.pdf",
            "application/pdf",
            12,
            content=b"%PDF-1.4\nabc",
            allowed_mimes=("application/pdf",),
            max_bytes=1024,
        )
        self.assertEqual(suffix, ".pdf")


# 以下类依赖 pytest 风格 fixture，verify.py 的 unittest discovery 不会实例化；
# 实际端到端场景由 test_billing_stats 与 live_api_check 覆盖。


def test_invoice_rejects_cross_asset_and_deleted_fee(client: TestClient, admin_headers) -> None:
    a = client.post(
        "/api/assets", json={"name": "案件A", "ip_type": "patent"}, headers=admin_headers
    ).json()
    b = client.post(
        "/api/assets", json={"name": "案件B", "ip_type": "patent"}, headers=admin_headers
    ).json()
    fee = client.post(
        "/api/fees",
        json={"ip_asset_id": b["id"], "fee_type": "agency", "amount_due": "100"},
        headers=admin_headers,
    ).json()
    cross = client.post(
        "/api/invoices",
        json={"ip_asset_id": a["id"], "invoice_no": "CROSS", "fee_ids": [fee["id"]]},
        headers=admin_headers,
    )
    assert cross.status_code == 422
    assert client.delete(f"/api/fees/{fee['id']}", headers=admin_headers).status_code == 204
    deleted = client.post(
        "/api/invoices",
        json={"ip_asset_id": b["id"], "invoice_no": "DELETED", "fee_ids": [fee["id"]]},
        headers=admin_headers,
    )
    assert deleted.status_code == 422


def test_material_preview_returns_image_and_page_count(client: TestClient, admin_headers) -> None:
    asset = client.post(
        "/api/assets",
        json={"name": "在线查看案件", "ip_type": "patent"},
        headers=admin_headers,
    ).json()
    content = b"\x89PNG\r\n\x1a\n" + b"inline-image"
    upload = client.post(
        "/api/materials",
        data={"ip_asset_id": asset["id"], "category": "certificate_scan"},
        files={"file": ("scan.png", io.BytesIO(content), "image/png")},
        headers=admin_headers,
    )
    assert upload.status_code == 201, upload.text

    response = client.get(f"/api/materials/{upload.json()['id']}/preview?page=0", headers=admin_headers)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/png"
    assert response.headers["x-page-count"] == "1"
    assert response.content == content


def test_material_upload_persists_remark_and_lists_it(client: TestClient, admin_headers) -> None:
    asset = client.post(
        "/api/assets",
        json={"name": "带备注材料案件", "ip_type": "patent"},
        headers=admin_headers,
    ).json()
    upload = client.post(
        "/api/materials",
        data={
            "ip_asset_id": asset["id"],
            "category": "certificate_scan",
            "remark": "证书原件存放于财务柜",
        },
        files={"file": ("remark.png", io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"remark"), "image/png")},
        headers=admin_headers,
    )
    assert upload.status_code == 201, upload.text
    assert upload.json()["remark"] == "证书原件存放于财务柜"

    items = client.get("/api/materials", headers=admin_headers).json()["items"]
    target = next(item for item in items if item["id"] == upload.json()["id"])
    assert target["remark"] == "证书原件存放于财务柜"


def test_replace_material_file_keeps_old_blob_and_resets_extraction(
    client: TestClient, admin_headers, db_session
) -> None:
    from app.models import ExtractionStatus, Material
    from app.storage import get_storage

    asset = client.post(
        "/api/assets",
        json={"name": "更换文件案件", "ip_type": "patent"},
        headers=admin_headers,
    ).json()
    upload = client.post(
        "/api/materials",
        data={"ip_asset_id": asset["id"], "category": "certificate_scan", "remark": "旧备注"},
        files={"file": ("old.png", io.BytesIO(b"\x89PNG\r\n\x1a\nold"), "image/png")},
        headers=admin_headers,
    )
    assert upload.status_code == 201, upload.text
    old = upload.json()

    material = db_session.get(Material, old["id"])
    old_storage_key = material.storage_key
    material.extraction_status = ExtractionStatus.SUCCEEDED
    material.extraction_kind = "certificate"
    material.extraction_fields = {"fields": {"name": "旧值"}}
    material.extraction_text = "旧识别文本"
    db_session.commit()
    storage = get_storage()
    assert storage.exists(old_storage_key)

    new_content = b"%PDF-1.4\n" + b"replacement"
    replaced = client.post(
        f"/api/materials/{old['id']}/replace",
        data={"remark": "新备注"},
        files={"file": ("new.pdf", io.BytesIO(new_content), "application/pdf")},
        headers=admin_headers,
    )
    assert replaced.status_code == 200, replaced.text
    body = replaced.json()
    assert body["original_name"] == "new.pdf"
    assert body["display_name"] == "new.pdf"
    assert body["remark"] == "新备注"
    assert body["size_bytes"] == len(new_content)
    assert body["sha256"] != old["sha256"]
    assert body["extraction_status"] == "none"
    assert body["extraction_kind"] is None
    assert body["extraction_fields"] is None

    db_session.refresh(material)
    assert material.storage_key != old_storage_key
    assert storage.exists(old_storage_key), "旧文件按保留策略不应被删除"
    assert storage.exists(material.storage_key)

    logs = client.get(
        "/api/audit-logs?object_type=material&action=replace_file", headers=admin_headers
    ).json()
    assert any(item["object_id"] == old["id"] for item in logs["items"])


def test_viewer_cannot_replace_material_file(client: TestClient, admin_headers, viewer_headers) -> None:
    asset = client.post(
        "/api/assets", json={"name": "只读更换案件", "ip_type": "patent"}, headers=admin_headers
    ).json()
    upload = client.post(
        "/api/materials",
        data={"ip_asset_id": asset["id"], "category": "certificate_scan"},
        files={"file": ("old.png", io.BytesIO(b"\x89PNG\r\n\x1a\nold"), "image/png")},
        headers=admin_headers,
    )
    assert upload.status_code == 201, upload.text

    response = client.post(
        f"/api/materials/{upload.json()['id']}/replace",
        files={"file": ("new.png", io.BytesIO(b"\x89PNG\r\n\x1a\nnew"), "image/png")},
        headers=viewer_headers,
    )
    assert response.status_code == 403


def test_attachment_must_exist_and_match_asset(client: TestClient, admin_headers) -> None:
    a = client.post(
        "/api/assets", json={"name": "案件A", "ip_type": "patent"}, headers=admin_headers
    ).json()
    b = client.post(
        "/api/assets", json={"name": "案件B", "ip_type": "patent"}, headers=admin_headers
    ).json()
    upload = client.post(
        "/api/materials",
        data={"ip_asset_id": b["id"], "category": "invoice"},
        files={"file": ("invoice.pdf", io.BytesIO(b"%PDF-1.4\nabc"), "application/pdf")},
        headers=admin_headers,
    )
    assert upload.status_code == 201, upload.text
    mismatch = client.post(
        "/api/invoices",
        json={
            "ip_asset_id": a["id"],
            "invoice_no": "BAD-MATERIAL",
            "file_material_id": upload.json()["id"],
        },
        headers=admin_headers,
    )
    assert mismatch.status_code == 422
    missing = client.post(
        "/api/invoices",
        json={"ip_asset_id": a["id"], "invoice_no": "MISSING", "file_material_id": "missing"},
        headers=admin_headers,
    )
    assert missing.status_code == 422


class MaterialRecognizableTest(unittest.TestCase):
    def test_pdf_and_image_are_recognizable(self) -> None:
        for ext in ("pdf", "png", "jpg", "jpeg", "webp"):
            ensure_recognizable(SimpleNamespace(ext=ext, original_name=f"x.{ext}"))

    def test_office_and_archive_are_rejected(self) -> None:
        for ext in ("docx", "xlsx", "zip", "txt"):
            with self.assertRaises(HTTPException) as context:
                ensure_recognizable(SimpleNamespace(ext=ext, original_name=f"x.{ext}"))
            assert context.exception.status_code == 422


if __name__ == "__main__":
    unittest.main()
