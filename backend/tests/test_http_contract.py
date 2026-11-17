"""HTTP 层契约测试（需要 fastapi + httpx，不需要数据库）。

目的：验证前端依赖的响应格式与错误格式，而不是只验证 Python 对象。

    python -m unittest discover -s backend/tests -t backend -p "test_http_contract.py"

重点断言：
- 金额以字符串序列化（前端按字符串展示）；
- 枚举序列化为值（如 "paid"），不是枚举名；
- 日期为 YYYY-MM-DD，时间为带时区 ISO 8601；
- 请求校验失败时返回 FastAPI 标准结构 {"detail": [{...}]}。
"""

from __future__ import annotations

import json
import unittest
from decimal import Decimal

try:  # pragma: no cover - 环境相关
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover
    raise unittest.SkipTest("未安装 fastapi/httpx，跳过 HTTP 契约测试") from None

from app.schemas import FeeOut, Page, FeeIn

app = FastAPI()


@app.post("/api/fees", response_model=FeeOut)
def create_fee(payload: FeeIn) -> FeeOut:
    """仅用于验证序列化与错误格式，不接数据库。"""

    status = "paid" if payload.amount_paid and payload.amount_paid >= payload.amount_due else "unpaid"
    return FeeOut(
        id="fee-1",
        fee_type=payload.fee_type,
        amount_due=payload.amount_due,
        amount_paid=payload.amount_paid,
        currency=payload.currency,
        status=status,
    )


@app.get("/api/fees", response_model=Page[FeeOut])
def list_fees() -> Page[FeeOut]:
    return Page[FeeOut](items=[], total=0, page=1, page_size=20)


class FeeSerializationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_amount_serialized_as_string(self) -> None:
        response = self.client.post(
            "/api/fees", json={"fee_type": "agency", "amount_due": "8000.00", "amount_paid": "8000.00"}
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertIsInstance(body["amount_due"], str, "金额应序列化为字符串，前端按字符串展示")
        self.assertEqual(body["amount_due"], "8000.00")

    def test_enum_serialized_as_value(self) -> None:
        response = self.client.post("/api/fees", json={"fee_type": "annuity", "amount_due": "1.00"})
        body = response.json()
        self.assertEqual(body["fee_type"], "annuity")
        self.assertEqual(body["status"], "unpaid")

    def test_validation_error_shape_for_frontend(self) -> None:
        """前端会读取 body.detail 或 body.detail[0].msg，这里锁定该结构。"""

        response = self.client.post("/api/fees", json={"fee_type": "agency", "amount_due": "-5"})
        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertIn("detail", body)
        self.assertIsInstance(body["detail"], list)
        self.assertIn("msg", body["detail"][0])
        self.assertIn("loc", body["detail"][0])

    def test_unknown_enum_rejected(self) -> None:
        response = self.client.post("/api/fees", json={"fee_type": "unknown", "amount_due": "1.00"})
        self.assertEqual(response.status_code, 422)

    def test_page_envelope(self) -> None:
        body = self.client.get("/api/fees").json()
        self.assertEqual(set(body), {"items", "total", "page", "page_size"})
        self.assertEqual(body["items"], [])

    def test_openapi_schema_generation(self) -> None:
        schema = app.openapi()
        self.assertIn("/api/fees", schema["paths"])
        fee_schema = schema["components"]["schemas"]["FeeOut"]
        self.assertIn("amount_due", fee_schema["properties"])
        # 金额字段默认为字符串类型，与前端约定一致
        self.assertEqual(fee_schema["properties"]["amount_due"].get("type"), "string")


class DateSerializationTest(unittest.TestCase):
    def test_date_format(self) -> None:
        from app.schemas import DateItemOut

        item = DateItemOut(
            id="d1",
            title="示例",
            date_type="due",
            due_date="2026-11-12",
            source="manual",
            needs_confirmation=False,
            status="open",
        )
        payload = json.loads(item.model_dump_json())
        self.assertEqual(payload["due_date"], "2026-11-12")
        self.assertEqual(payload["date_type"], "due")
        self.assertFalse(payload["needs_confirmation"])


class DecimalPrecisionTest(unittest.TestCase):
    def test_trailing_zero_preserved(self) -> None:
        model = FeeOut(id="f", fee_type="agency", amount_due=Decimal("100.50"), currency="CNY", status="unpaid")
        self.assertEqual(json.loads(model.model_dump_json())["amount_due"], "100.50")


if __name__ == "__main__":
    unittest.main()
