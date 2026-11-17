"""关联业务资源可见性测试。

取消部门后，所有登录用户都能查看全部档案及其关联资源；写操作仍受角色限制。

    python -m unittest backend.tests.test_resource_access
"""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import security
from app.database import Base, get_db
from app.main import app
from app.models import User, UserRole


class RelatedResourceAccessTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        TestingSession = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        self.db = TestingSession()

        def override_get_db():
            yield self.db

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

        admin = User(
            username="access-admin",
            display_name="管理员",
            password_hash=security.hash_password("Passw0rd!"),
            role=UserRole.ADMIN,
        )
        viewer = User(
            username="access-viewer",
            display_name="查看者",
            password_hash=security.hash_password("Passw0rd!"),
            role=UserRole.USER,
        )
        self.db.add_all([admin, viewer])
        self.db.commit()
        self.admin_headers = self._login("access-admin")
        self.viewer_headers = self._login("access-viewer")

        self.asset_a = self._asset("案件 A")
        self.asset_b = self._asset("案件 B")
        self._seed_related(self.asset_a)
        self._seed_related(self.asset_b)

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _login(self, username: str) -> dict[str, str]:
        response = self.client.post(
            "/api/auth/login", json={"username": username, "password": "Passw0rd!"}
        )
        self.assertEqual(response.status_code, 200, response.text)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def _asset(self, name: str) -> str:
        response = self.client.post(
            "/api/assets",
            json={"name": name, "ip_type": "patent"},
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["id"]

    def _seed_related(self, asset_id: str) -> None:
        responses = [
            self.client.post(
                "/api/fees",
                json={"ip_asset_id": asset_id, "fee_type": "agency", "amount_due": "100.00"},
                headers=self.admin_headers,
            ),
            self.client.post(
                "/api/dates",
                json={"ip_asset_id": asset_id, "title": "测试日期", "date_type": "custom"},
                headers=self.admin_headers,
            ),
            self.client.post(
                "/api/certificates",
                json={"ip_asset_id": asset_id, "cert_type": "patent_certificate"},
                headers=self.admin_headers,
            ),
        ]
        for response in responses:
            self.assertLess(response.status_code, 300, response.text)

    def test_viewer_sees_all_related_resources(self) -> None:
        for path in ("/api/fees", "/api/dates", "/api/certificates"):
            body = self.client.get(path, headers=self.viewer_headers).json()
            self.assertEqual(body["total"], 2, (path, body))
            self.assertEqual(
                {item["ip_asset_id"] for item in body["items"]}, {self.asset_a, self.asset_b}
            )

    def test_viewer_can_filter_by_any_asset(self) -> None:
        for path in ("fees", "dates", "certificates", "materials", "invoices"):
            response = self.client.get(
                f"/api/{path}?ip_asset_id={self.asset_b}", headers=self.viewer_headers
            )
            self.assertNotEqual(response.status_code, 404, (path, response.text))

    def test_viewer_can_read_any_asset_detail(self) -> None:
        response = self.client.get(f"/api/assets/{self.asset_b}", headers=self.viewer_headers)
        self.assertEqual(response.status_code, 200, response.text)

    def test_dashboard_counts_all_assets(self) -> None:
        body = self.client.get("/api/stats/dashboard", headers=self.viewer_headers).json()
        self.assertEqual(body["total_assets"], 2)
        self.assertEqual(sum(body["certificates_by_type"].values()), 2)

    def test_viewer_cannot_write(self) -> None:
        response = self.client.post(
            "/api/fees",
            json={"ip_asset_id": self.asset_a, "fee_type": "agency", "amount_due": "1.00"},
            headers=self.viewer_headers,
        )
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
