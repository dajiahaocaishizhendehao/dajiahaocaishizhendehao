"""档案关系、费用状态、发票去重与审计关联测试。"""
from fastapi.testclient import TestClient


def test_missing_party_and_person_rejected(client: TestClient, admin_headers) -> None:
    base = {"name": "关系校验", "ip_type": "patent"}
    party = client.post("/api/assets", json={**base, "parties": [{"party_id": "missing", "role": "patentee"}]}, headers=admin_headers)
    person = client.post("/api/assets", json={**base, "persons": [{"person_id": "missing", "role": "inventor"}]}, headers=admin_headers)
    assert party.status_code == 422
    assert person.status_code == 422


def test_contradictory_fee_status_rejected(client: TestClient, admin_headers) -> None:
    response = client.post("/api/fees", json={"fee_type": "agency", "amount_due": "100", "amount_paid": "0", "status": "paid"}, headers=admin_headers)
    assert response.status_code == 422


def test_invoice_duplicate_fee_ids_response_is_deduplicated(client: TestClient, admin_headers) -> None:
    fee = client.post("/api/fees", json={"fee_type": "agency", "amount_due": "1"}, headers=admin_headers).json()["id"]
    response = client.post("/api/invoices", json={"invoice_no": "DUP-FEE", "fee_ids": [fee, fee]}, headers=admin_headers)
    assert response.status_code == 201, response.text
    assert response.json()["fee_ids"] == [fee]


def test_create_fee_and_date_audit_have_object_id(client: TestClient, admin_headers) -> None:
    fee = client.post("/api/fees", json={"fee_type": "agency", "amount_due": "1"}, headers=admin_headers).json()
    date = client.post("/api/dates", json={"title": "日期", "date_type": "custom"}, headers=admin_headers).json()
    logs = client.get("/api/audit-logs", headers=admin_headers).json()["items"]
    by_summary = {item["summary"]: item for item in logs}
    assert by_summary["agency 1.00 CNY"]["object_id"] == fee["id"]
    assert by_summary["日期"]["object_id"] == date["id"]
