"""实用型工作台聚合测试。"""

from __future__ import annotations

import datetime

from fastapi.testclient import TestClient


def _asset(client: TestClient, headers, name: str) -> str:
    response = client.post(
        "/api/assets",
        json={
            "name": name,
            "ip_type": "patent",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_workbench_returns_actionable_items(client: TestClient, admin_headers) -> None:
    asset_id = _asset(client, admin_headers, "工作台测试案件")
    today = datetime.date.today()
    due = today + datetime.timedelta(days=3)
    client.post(
        "/api/dates",
        json={"ip_asset_id": asset_id, "title": "人工待办", "date_type": "due", "due_date": due.isoformat()},
        headers=admin_headers,
    )
    client.post(
        "/api/fees",
        json={
            "ip_asset_id": asset_id,
            "fee_type": "agency",
            "amount_due": "100.00",
            "amount_paid": "100.00",
            "paid_date": today.isoformat(),
        },
        headers=admin_headers,
    )

    response = client.get("/api/stats/workbench?due_soon_days=30", headers=admin_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_assets"] == 1
    assert body["in_progress_assets"] == 1
    assert body["pending_date_count"] == 1
    assert body["tasks"][0]["title"] == "人工待办"
    assert body["missing_invoice_fee_count"] == 1
    assert body["missing_invoice_fees"][0]["asset_name"] == "工作台测试案件"
    assert body["recent_assets"][0]["id"] == asset_id
    assert body["metrics"]


def test_workbench_empty_state(client: TestClient, admin_headers) -> None:
    body = client.get("/api/stats/workbench", headers=admin_headers).json()
    assert body["total_assets"] == 0
    assert body["tasks"] == []
    assert body["missing_invoice_fees"] == []
    assert body["extraction_attention"] == []
