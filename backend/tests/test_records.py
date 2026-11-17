"""证书与日期事项测试。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _create_asset(client: TestClient, headers) -> str:
    response = client.post(
        "/api/assets",
        json={
            "name": "一种模块化传感装置",
            "ip_type": "patent",
            "status_group": "granted",
            "patent": {"patent_type": "utility"},
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_certificate_tracks_electronic_and_paper_separately(client: TestClient, admin_headers) -> None:
    asset_id = _create_asset(client, admin_headers)
    response = client.post(
        "/api/certificates",
        json={
            "ip_asset_id": asset_id,
            "cert_type": "patent_certificate",
            "cert_no": "CERT-DEMO-001",
            "issue_date": "2025-12-18",
            "electronic_status": "archived",
            "paper_status": "in_storage",
            "location": "A柜-02层",
        },
        headers=admin_headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["electronic_status"] == "archived"
    assert body["paper_status"] == "in_storage"


def test_recipient_date_before_received_rejected(client: TestClient, admin_headers) -> None:
    asset_id = _create_asset(client, admin_headers)
    response = client.post(
        "/api/certificates",
        json={
            "ip_asset_id": asset_id,
            "cert_type": "patent_certificate",
            "received_date": "2026-01-10",
            "recipient_date": "2026-01-01",
        },
        headers=admin_headers,
    )
    assert response.status_code == 422


def test_date_list_returns_asset_name(client: TestClient, admin_headers) -> None:
    asset_id = _create_asset(client, admin_headers)
    created = client.post(
        "/api/dates",
        json={
            "ip_asset_id": asset_id,
            "title": "提交年费",
            "date_type": "due",
            "due_date": "2026-12-31",
        },
        headers=admin_headers,
    )
    assert created.status_code == 201, created.text

    response = client.get("/api/dates?page=1&page_size=20", headers=admin_headers)
    assert response.status_code == 200
    item = next(row for row in response.json()["items"] if row["title"] == "提交年费")
    assert item["ip_asset_id"] == asset_id
    assert item["asset_name"] == "一种模块化传感装置"
