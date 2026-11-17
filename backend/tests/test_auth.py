"""认证与权限测试。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    assert client.get("/health").json()["status"] == "ok"


def test_login_success(client: TestClient, admin_user) -> None:
    response = client.post("/api/auth/login", json={"username": "admin", "password": "Passw0rd!"})
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["role"] == "admin"


def test_login_wrong_password(client: TestClient, admin_user) -> None:
    response = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert response.status_code == 401
    assert response.json()["detail"] == "账号或密码错误"


def test_unknown_user_has_same_error(client: TestClient, admin_user) -> None:
    response = client.post("/api/auth/login", json={"username": "nobody", "password": "x"})
    assert response.status_code == 401
    assert response.json()["detail"] == "账号或密码错误"


def test_requires_token(client: TestClient) -> None:
    assert client.get("/api/assets").status_code == 401


def test_me(client: TestClient, admin_headers) -> None:
    response = client.get("/api/auth/me", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["username"] == "admin"


def test_logout_revokes_only_current_session(client: TestClient, admin_user) -> None:
    first = client.post("/api/auth/login", json={"username": "admin", "password": "Passw0rd!"})
    second = client.post("/api/auth/login", json={"username": "admin", "password": "Passw0rd!"})
    assert first.status_code == 200
    assert second.status_code == 200
    first_headers = {"Authorization": f"Bearer {first.json()['access_token']}"}
    second_headers = {"Authorization": f"Bearer {second.json()['access_token']}"}

    assert client.post("/api/auth/logout", headers=first_headers).status_code == 204
    assert client.get("/api/auth/me", headers=first_headers).status_code == 401
    assert client.get("/api/auth/me", headers=second_headers).status_code == 200
