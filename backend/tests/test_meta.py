"""基础资料与系统用户的增删改、逻辑删除和审计测试。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_party_update_and_delete_are_audited(client: TestClient, admin_headers) -> None:
    created = client.post(
        "/api/parties",
        json={"name": "示例权利人", "party_type": "company", "contact": "甲"},
        headers=admin_headers,
    )
    assert created.status_code == 201, created.text
    party = created.json()

    updated = client.patch(
        f"/api/parties/{party['id']}",
        json={
            "name": "示例权利人（更新）",
            "party_type": "person",
            "country": "中国",
            "contact": "乙",
            "phone": "13800000000",
            "email": "party@example.com",
            "is_default": True,
        },
        headers=admin_headers,
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["name"] == "示例权利人（更新）"
    assert body["party_type"] == "person"
    assert body["phone"] == "13800000000"

    deleted = client.delete(f"/api/parties/{party['id']}", headers=admin_headers)
    assert deleted.status_code == 204
    assert all(item["id"] != party["id"] for item in client.get("/api/parties", headers=admin_headers).json()["items"])

    logs = client.get("/api/audit-logs?object_type=party", headers=admin_headers).json()
    actions = {item["action"] for item in logs["items"]}
    assert {"create", "update", "delete"} <= actions


def test_party_partial_update_preserves_other_fields(client: TestClient, admin_headers) -> None:
    created = client.post(
        "/api/parties",
        json={
            "name": "部分更新演示权利人",
            "party_type": "company",
            "country": "中国",
            "contact": "甲",
            "phone": "13800000001",
        },
        headers=admin_headers,
    )
    assert created.status_code == 201, created.text
    party = created.json()

    updated = client.patch(
        f"/api/parties/{party['id']}",
        json={"name": "部分更新演示权利人（改名）"},
        headers=admin_headers,
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["name"] == "部分更新演示权利人（改名）"
    assert body["country"] == "中国"
    assert body["contact"] == "甲"
    assert body["phone"] == "13800000001"
    assert body["party_type"] == "company"


def test_agency_and_project_update_and_delete(client: TestClient, admin_headers, admin_user) -> None:
    agency = client.post(
        "/api/agencies",
        json={"name": "示例代理机构", "service_type": "专利代理"},
        headers=admin_headers,
    ).json()
    updated_agency = client.patch(
        f"/api/agencies/{agency['id']}",
        json={"name": "示例代理机构（更新）", "service_type": "商标代理", "phone": "010-12345678"},
        headers=admin_headers,
    )
    assert updated_agency.status_code == 200, updated_agency.text
    assert updated_agency.json()["service_type"] == "商标代理"
    assert client.delete(f"/api/agencies/{agency['id']}", headers=admin_headers).status_code == 204

    project = client.post(
        "/api/projects",
        json={"name": "示例项目", "code": "PRJ-META-1", "owner_user_id": admin_user.id},
        headers=admin_headers,
    ).json()
    assert project["owner_display_name"] == "管理员"
    updated_project = client.patch(
        f"/api/projects/{project['id']}",
        json={"name": "示例项目（更新）", "code": "PRJ-META-1", "owner_user_id": admin_user.id, "status": "进行中"},
        headers=admin_headers,
    )
    assert updated_project.status_code == 200, updated_project.text
    assert updated_project.json()["status"] == "进行中"
    assert updated_project.json()["owner_display_name"] == "管理员"
    assert client.delete(f"/api/projects/{project['id']}", headers=admin_headers).status_code == 204


def test_project_code_must_remain_unique_on_update(client: TestClient, admin_headers) -> None:
    first = client.post("/api/projects", json={"name": "项目一", "code": "PRJ-META-2"}, headers=admin_headers).json()
    second = client.post("/api/projects", json={"name": "项目二", "code": "PRJ-META-3"}, headers=admin_headers).json()
    response = client.patch(
        f"/api/projects/{second['id']}",
        json={"name": "项目二", "code": first["code"]},
        headers=admin_headers,
    )
    assert response.status_code == 409


def test_viewer_cannot_modify_basic_data(client: TestClient, viewer_headers) -> None:
    assert (
        client.patch(
            "/api/parties/missing",
            json={"name": "无权修改"},
            headers=viewer_headers,
        ).status_code
        == 403
    )
    assert client.delete("/api/agencies/missing", headers=viewer_headers).status_code == 403
    assert client.delete("/api/users/missing", headers=viewer_headers).status_code == 403


def test_delete_user_is_logical_and_revokes_sessions(client: TestClient, admin_headers) -> None:
    created = client.post(
        "/api/users",
        json={
            "username": "delete-me",
            "display_name": "待删除用户",
            "password": "Passw0rd!",
            "role": "user",
        },
        headers=admin_headers,
    )
    assert created.status_code == 201, created.text
    user = created.json()

    login = client.post("/api/auth/login", json={"username": "delete-me", "password": "Passw0rd!"})
    assert login.status_code == 200
    user_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/api/auth/me", headers=user_headers).status_code == 200

    deleted = client.delete(f"/api/users/{user['id']}", headers=admin_headers)
    assert deleted.status_code == 204
    assert client.get("/api/auth/me", headers=user_headers).status_code == 401
    assert all(
        item["id"] != user["id"] for item in client.get("/api/users", headers=admin_headers).json()["items"]
    )

    logs = client.get("/api/audit-logs?object_type=user&action=delete", headers=admin_headers).json()
    assert any(item["object_id"] == user["id"] for item in logs["items"])


def test_admin_cannot_delete_self(client: TestClient, admin_headers, admin_user) -> None:
    response = client.delete(f"/api/users/{admin_user.id}", headers=admin_headers)
    assert response.status_code == 422
    assert "当前登录账号" in response.json()["detail"]


def test_admin_cannot_demote_or_deactivate_self(client: TestClient, admin_headers, admin_user) -> None:
    demote = client.patch(
        f"/api/users/{admin_user.id}", json={"role": "user"}, headers=admin_headers
    )
    assert demote.status_code == 422
    assert "角色" in demote.json()["detail"]

    deactivate = client.patch(
        f"/api/users/{admin_user.id}", json={"is_active": False}, headers=admin_headers
    )
    assert deactivate.status_code == 422
    assert "停用" in deactivate.json()["detail"]
