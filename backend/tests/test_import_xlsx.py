"""CSV/XLSX 导入与专业子对象测试。"""
from __future__ import annotations
import datetime
import io
from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook


def xlsx_bytes(rows: list[list[object]]) -> bytes:
    workbook = Workbook(); sheet = workbook.active
    for row in rows: sheet.append(row)
    buffer = io.BytesIO(); workbook.save(buffer); return buffer.getvalue()


def test_import_template_uses_confirmed_columns(client: TestClient, admin_headers) -> None:
    response = client.get("/api/import/assets/template.xlsx", headers=admin_headers)
    assert response.status_code == 200, response.text
    workbook = load_workbook(io.BytesIO(response.content))
    headers = [cell.value for cell in workbook.worksheets[0][1]]
    assert headers == [
        "我方文号",
        "申请号",
        "案件名称",
        "专利所有权人",
        "官费应缴纳日",
        "本次官费缴纳至",
        "本次官费缴纳金额",
        "缴纳日期",
    ]


def test_chinese_template_imports_patent_owner_and_fee(client: TestClient, admin_headers) -> None:
    content = xlsx_bytes([
        ["我方文号", "申请号", "案件名称", "专利所有权人", "官费应缴纳日", "本次官费缴纳至", "本次官费缴纳金额", "缴纳日期"],
        ["STHL-1", "202610000001.0", "一种测试案件", "思腾合力", datetime.date(2026, 1, 1), datetime.date(2026, 12, 31), 1200.0, datetime.date(2026, 1, 5)],
        ["", "", "仅填写案件名称", "", "", "", "", ""],
    ])
    response = client.post(
        "/api/import/assets",
        files={"file": ("assets.xlsx", io.BytesIO(content), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["created"] == 2
    assert response.json()["skipped"] == 0

    item = client.get("/api/assets?q=一种测试案件", headers=admin_headers).json()["items"][0]
    detail = client.get(f"/api/assets/{item['id']}", headers=admin_headers).json()
    assert detail["docket_no"] == "STHL-1"
    assert detail["ip_type"] == "patent"
    assert detail["patent"]["application_no"] == "202610000001.0"
    assert [party["name"] for party in detail["parties"]] == ["思腾合力"]

    fees = client.get(f"/api/fees?ip_asset_id={item['id']}", headers=admin_headers).json()
    assert fees["total"] == 1
    fee = fees["items"][0]
    assert fee["fee_type"] == "annuity"
    assert fee["amount_due"] == "1200.00"
    assert fee["amount_paid"] == "1200.00"
    assert fee["status"] == "paid"
    assert fee["due_date"] == "2026-01-01"
    assert fee["coverage_end_date"] == "2026-12-31"
    assert fee["paid_date"] == "2026-01-05"

    only_name = client.get("/api/assets?q=仅填写案件名称", headers=admin_headers).json()["items"][0]
    assert "asset_no" not in only_name
    only_detail = client.get(f"/api/assets/{only_name['id']}", headers=admin_headers).json()
    assert only_detail["parties"] == []
    assert client.get(f"/api/fees?ip_asset_id={only_name['id']}", headers=admin_headers).json()["total"] == 0


def test_chinese_csv_accepts_case_name_only(client: TestClient, admin_headers) -> None:
    csv_data = (
        "我方文号,申请号,案件名称,专利所有权人,官费应缴纳日,本次官费缴纳至,本次官费缴纳金额,缴纳日期\n"
        ",,CSV 仅名称案件,,,,,\n"
    ).encode("utf-8")
    response = client.post(
        "/api/import/assets",
        files={"file": ("assets.csv", io.BytesIO(csv_data), "text/csv")},
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["created"] == 1
    assert response.json()["skipped"] == 0
    item = client.get("/api/assets?q=CSV 仅名称案件", headers=admin_headers).json()["items"][0]
    assert "asset_no" not in item
    assert item["docket_no"] is None


def test_xlsx_import_creates_professional_rows(client: TestClient, admin_headers) -> None:
    content = xlsx_bytes([
        ["asset_no", "name", "ip_type", "status_group"],
        ["XL-PAT", "Excel专利", "patent", "in_progress"],
        ["XL-SW", "Excel软著", "copyright", "granted"],
        ["XL-TM", "Excel商标", "trademark", "in_progress"],
    ])
    response = client.post(
        "/api/import/assets",
        files={"file": ("assets.xlsx", io.BytesIO(content), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["created"] == 3
    for name, field in (("Excel专利", "patent"), ("Excel软著", "copyright"), ("Excel商标", "trademark")):
        item = client.get(f"/api/assets?q={name}", headers=admin_headers).json()["items"][0]
        detail = client.get(f"/api/assets/{item['id']}", headers=admin_headers).json()
        assert detail[field] is not None


def test_legacy_asset_no_column_is_ignored(client: TestClient, admin_headers) -> None:
    csv_data = "asset_no,name,ip_type,status_group\nDUP-X,旧模板案件,patent,in_progress\n".encode("utf-8")
    result = client.post(
        "/api/import/assets",
        files={"file": ("assets.csv", io.BytesIO(csv_data), "text/csv")},
        headers=admin_headers,
    ).json()
    assert result["created"] == 1
    assert result["skipped"] == 0
    item = client.get("/api/assets?q=旧模板案件", headers=admin_headers).json()["items"][0]
    assert "asset_no" not in item
