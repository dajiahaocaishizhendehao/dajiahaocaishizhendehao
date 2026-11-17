"""Pydantic 请求/响应模型的真实校验测试。

需要 pydantic（不需要 SQLAlchemy、数据库或 pytest）：

    python -m unittest discover -s backend/tests -t backend -p "test_schemas.py"

没有安装 pydantic 时整个模块会跳过，而不是报错。
"""

from __future__ import annotations

import datetime
import unittest
from decimal import Decimal

try:  # pragma: no cover - 环境相关
    from pydantic import ValidationError
except ImportError:  # pragma: no cover
    raise unittest.SkipTest("未安装 pydantic，跳过模型契约测试") from None

from app.schemas import (
    AssetCreate,
    AssetDetail,
    CertificateIn,
    DateItemIn,
    FeeIn,
    InvoiceIn,
    PatentIn,
    TrademarkIn,
    UserCreate,
)


class AssetCreateTest(unittest.TestCase):
    def test_valid_patent_payload(self) -> None:
        model = AssetCreate(
            name="一种示例方法",
            ip_type="patent",
            patent={"patent_type": "invention", "application_date": "2025-03-18"},
        )
        self.assertEqual(model.ip_type.value, "patent")
        self.assertEqual(model.status_group.value, "in_progress")
        self.assertIsNotNone(model.patent)
        self.assertEqual(model.parties, [])

    def test_requires_name_only(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            AssetCreate(name="", ip_type="patent")
        fields = {error["loc"][0] for error in ctx.exception.errors()}
        self.assertEqual(fields, {"name"})

    def test_unknown_type_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            AssetCreate(name="B", ip_type="design_patent")

    def test_patent_grant_before_application_rejected(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            PatentIn(application_date=datetime.date(2025, 3, 18), grant_date=datetime.date(2024, 1, 1))
        self.assertIn("授权日期不能早于申请日期", str(ctx.exception))

    def test_patent_grant_equal_to_application_allowed(self) -> None:
        model = PatentIn(
            application_date=datetime.date(2025, 3, 18), grant_date=datetime.date(2025, 3, 18)
        )
        self.assertEqual(model.grant_date, datetime.date(2025, 3, 18))


class TrademarkTest(unittest.TestCase):
    def test_valid_to_before_valid_from_rejected(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            TrademarkIn(valid_from=datetime.date(2030, 1, 1), valid_to=datetime.date(2029, 1, 1))
        self.assertIn("有效期截止日期不能早于起始日期", str(ctx.exception))

    def test_classes_accepts_list(self) -> None:
        model = TrademarkIn(classes=["第 9 类", "第 42 类"])
        self.assertEqual(model.classes, ["第 9 类", "第 42 类"])


class CertificateTest(unittest.TestCase):
    def test_recipient_before_received_rejected(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            CertificateIn(
                ip_asset_id="asset-1",
                cert_type="patent_certificate",
                received_date=datetime.date(2026, 1, 10),
                recipient_date=datetime.date(2026, 1, 1),
            )
        self.assertIn("领取日期不能早于收到日期", str(ctx.exception))

    def test_defaults(self) -> None:
        model = CertificateIn(ip_asset_id="asset-1", cert_type="trademark_certificate")
        self.assertEqual(model.electronic_status.value, "pending")
        self.assertEqual(model.paper_status.value, "not_received")


class FeeAndInvoiceTest(unittest.TestCase):
    def test_negative_amount_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            FeeIn(fee_type="agency", amount_due=Decimal("-1"))

    def test_too_many_decimals_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            FeeIn(fee_type="agency", amount_due=Decimal("1.234"))

    def test_currency_length_enforced(self) -> None:
        with self.assertRaises(ValidationError):
            FeeIn(fee_type="agency", amount_due=Decimal("1.00"), currency="RMBX")

    def test_invoice_defaults(self) -> None:
        model = InvoiceIn(invoice_no="DEMO-INV-1")
        self.assertEqual(model.currency, "CNY")
        self.assertEqual(model.fee_ids, [])
        self.assertEqual(model.reimbursement_status.value, "not_submitted")


class DateItemTest(unittest.TestCase):
    def test_defaults_are_manual_and_unconfirmed(self) -> None:
        model = DateItemIn(title="示例事项", date_type="due")
        self.assertEqual(model.source.value, "manual")
        self.assertFalse(model.needs_confirmation)

    def test_empty_title_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            DateItemIn(title="", date_type="due")


class UserCreateTest(unittest.TestCase):
    def test_short_password_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            UserCreate(username="abc", display_name="甲", password="short")

    def test_default_role_is_user(self) -> None:
        model = UserCreate(username="abc", display_name="甲", password="Passw0rd!")
        self.assertEqual(model.role.value, "user")


class ORMModeTest(unittest.TestCase):
    def test_asset_detail_from_attributes(self) -> None:
        class Stub:
            id = "asset-1"
            name = "示例"
            ip_type = "patent"
            status_group = "granted"
            owner_user_id = None
            project_id = None
            remark = None
            created_at = datetime.datetime(2026, 11, 5, tzinfo=datetime.timezone.utc)
            updated_at = datetime.datetime(2026, 11, 5, tzinfo=datetime.timezone.utc)
            patent = None
            copyright = None
            trademark = None

        detail = AssetDetail.model_validate(Stub())
        self.assertEqual(detail.name, "示例")
        self.assertEqual(detail.parties, [])


class JsonSchemaTest(unittest.TestCase):
    def test_models_can_generate_json_schema(self) -> None:
        for model in (AssetCreate, CertificateIn, FeeIn, InvoiceIn, DateItemIn):
            schema = model.model_json_schema()
            self.assertIn("properties", schema)


if __name__ == "__main__":
    unittest.main()
