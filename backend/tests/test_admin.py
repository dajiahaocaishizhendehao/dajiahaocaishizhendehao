"""系统管理测试：用户、审计、导出与导入。"""

from __future__ import annotations

import io

from fastapi.testclient import TestClient


def test_only_admin_can_list_users(client: TestClient, viewer_headers) -> None:
    assert client.get("/api/users", headers=viewer_headers).status_code == 403


def test_create_user_and_reject_duplicate(client: TestClient, admin_headers) -> None:
    payload = {
        "username": "zhangsan",
        "display_name": "张三",
        "password": "Passw0rd!",
        "role": "ip_admin",
    }
    created = client.post("/api/users", json=payload, headers=admin_headers)
    assert created.status_code == 201, created.text
    assert created.json()["role"] == "ip_admin"

    duplicate = client.post("/api/users", json=payload, headers=admin_headers)
    assert duplicate.status_code == 409


def test_password_never_returned_or_logged(client: TestClient, admin_headers) -> None:
    client.post(
        "/api/users",
        json={"username": "lisi", "display_name": "李四", "password": "Secret123!", "role": "user"},
        headers=admin_headers,
    )
    users = client.get("/api/users", headers=admin_headers).json()
    assert all("password" not in item for item in users["items"])

    logs = client.get("/api/audit-logs?object_type=user", headers=admin_headers).json()
    assert logs["total"] >= 1
    assert "Secret123!" not in str(logs)


def test_user_search_and_edit_contact_fields(client: TestClient, admin_headers) -> None:
    created = client.post(
        "/api/users",
        json={
            "username": "search-target",
            "display_name": "检索目标",
            "password": "Passw0rd!",
            "role": "user",
            "phone": "13800000000",
            "email": "before@example.com",
        },
        headers=admin_headers,
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]

    found = client.get("/api/users?q=检索目标", headers=admin_headers).json()
    assert found["total"] == 1
    assert found["items"][0]["username"] == "search-target"
    assert found["items"][0]["phone"] == "13800000000"

    updated = client.patch(
        f"/api/users/{user_id}",
        json={
            "display_name": "检索目标（改）",
            "phone": None,
            "email": "after@example.com",
            "is_active": False,
        },
        headers=admin_headers,
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["display_name"] == "检索目标（改）"
    assert body["phone"] is None
    assert body["email"] == "after@example.com"
    assert body["is_active"] is False


def test_audit_log_written_for_asset_creation(client: TestClient, admin_headers) -> None:
    client.post(
        "/api/assets",
        json={"name": "审计测试专利", "ip_type": "patent"},
        headers=admin_headers,
    )
    logs = client.get("/api/audit-logs?object_type=ip_asset&action=create", headers=admin_headers).json()
    assert logs["total"] == 1


def test_export_writes_audit_and_returns_csv(client: TestClient, admin_headers) -> None:
    client.post(
        "/api/assets",
        json={"name": "导出测试", "ip_type": "patent"},
        headers=admin_headers,
    )
    response = client.get("/api/export/assets.csv", headers=admin_headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "导出测试" in response.text

    logs = client.get("/api/audit-logs?action=export", headers=admin_headers).json()
    assert logs["total"] == 1


def test_import_reports_row_errors(client: TestClient, admin_headers) -> None:
    # 旧模板的 asset_no 列保留但不解析：重复编号不再报错。
    content = (
        "asset_no,name,ip_type,status_group\n"
        "DEMO-PAT-9101,导入专利一,patent,in_progress\n"
        "DEMO-PAT-9101,重复编号不再报错,patent,in_progress\n"
        "DEMO-PAT-9102,,patent,in_progress\n"
        "DEMO-PAT-9103,未知类型,unknown,in_progress\n"
    )
    files = {"file": ("assets.csv", io.BytesIO(content.encode("utf-8")), "text/csv")}
    result = client.post("/api/import/assets", files=files, headers=admin_headers)
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["created"] == 2
    assert body["skipped"] == 2
    assert len(body["errors"]) == 2


def test_import_requires_columns(client: TestClient, admin_headers) -> None:
    files = {"file": ("bad.csv", io.BytesIO("我方文号,申请号\nA,202610000001.0\n".encode("utf-8")), "text/csv")}
    response = client.post("/api/import/assets", files=files, headers=admin_headers)
    assert response.status_code == 422
    assert "案件名称" in response.json()["detail"]
