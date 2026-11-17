"""费用、发票与统计口径测试。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_fee_status_derived_from_paid_amount(client: TestClient, admin_headers) -> None:
    unpaid = client.post(
        "/api/fees",
        json={"fee_type": "agency", "amount_due": "8000.00", "currency": "CNY"},
        headers=admin_headers,
    )
    assert unpaid.status_code == 201, unpaid.text
    assert unpaid.json()["status"] == "unpaid"

    partial = client.post(
        "/api/fees",
        json={"fee_type": "agency", "amount_due": "8000.00", "amount_paid": "3000.00"},
        headers=admin_headers,
    )
    assert partial.json()["status"] == "partial"

    paid = client.post(
        "/api/fees",
        json={"fee_type": "agency", "amount_due": "8000.00", "amount_paid": "8000.00"},
        headers=admin_headers,
    )
    assert paid.json()["status"] == "paid"


def test_invoice_links_multiple_fees(client: TestClient, admin_headers) -> None:
    fee_a = client.post(
        "/api/fees", json={"fee_type": "agency", "amount_due": "100.00"}, headers=admin_headers
    ).json()["id"]
    fee_b = client.post(
        "/api/fees", json={"fee_type": "material", "amount_due": "50.00"}, headers=admin_headers
    ).json()["id"]

    response = client.post(
        "/api/invoices",
        json={
            "invoice_no": "DEMO-INV-0001",
            "amount_gross": "150.00",
            "fee_ids": [fee_a, fee_b],
        },
        headers=admin_headers,
    )
    assert response.status_code == 201, response.text
    assert sorted(response.json()["fee_ids"]) == sorted([fee_a, fee_b])

    listing = client.get("/api/invoices", headers=admin_headers).json()
    assert listing["total"] == 1
    assert len(listing["items"][0]["fee_ids"]) == 2


def test_dashboard_returns_metric_definitions(client: TestClient, admin_headers) -> None:
    client.post(
        "/api/assets",
        json={"name": "演示专利", "ip_type": "patent"},
        headers=admin_headers,
    )
    body = client.get("/api/stats/dashboard", headers=admin_headers).json()
    assert body["total_assets"] == 1
    assert body["by_type"]["patent"] == 1
    assert body["due_soon_days"] >= 1
    keys = {metric["key"] for metric in body["metrics"]}
    assert {"total_assets", "by_type", "due_soon"} <= keys
