"""纯业务规则单元测试。

只依赖标准库与 app.domain / app.constants，可在未安装第三方依赖时直接运行：

    python -m unittest discover -s backend/tests -t backend -p "test_domain.py"

pytest 也会正常收集这些 TestCase。
"""

from __future__ import annotations

import datetime
import unittest
from decimal import Decimal

from app.constants import FeeStatus, IpType
from app.domain import (
    DomainError,
    derive_fee_status,
    due_soon_window,
    ensure_date_order,
    granted_rate,
    group_counts_by_year,
    parse_decimal,
    parse_import_row,
    parse_import_rows,
    percentage,
    validate_certificate_dates,
    validate_type_payload,
    validate_upload,
)


class ValidateTypePayloadTest(unittest.TestCase):
    def test_matching_type_is_accepted(self) -> None:
        validate_type_payload(IpType.PATENT, {"a": 1}, None, None)
        validate_type_payload(IpType.COPYRIGHT, None, {"b": 2}, None)
        validate_type_payload(IpType.TRADEMARK, None, None, {"c": 3})

    def test_empty_payload_is_accepted(self) -> None:
        for ip_type in IpType:
            validate_type_payload(ip_type, None, None, None)

    def test_cross_type_payload_is_rejected(self) -> None:
        with self.assertRaises(DomainError) as ctx:
            validate_type_payload(IpType.PATENT, {"a": 1}, None, {"trademark": True})
        self.assertIn("trademark", str(ctx.exception))

    def test_two_foreign_payloads_rejected(self) -> None:
        with self.assertRaises(DomainError):
            validate_type_payload(IpType.PATENT, None, {"b": 1}, {"c": 1})


class DeriveFeeStatusTest(unittest.TestCase):
    def test_unpaid_when_nothing_paid(self) -> None:
        self.assertIs(derive_fee_status(Decimal("100.00"), None), FeeStatus.UNPAID)
        self.assertIs(derive_fee_status(Decimal("100.00"), Decimal("0.00")), FeeStatus.UNPAID)

    def test_partial_payment(self) -> None:
        self.assertIs(derive_fee_status(Decimal("100.00"), Decimal("30.00")), FeeStatus.PARTIAL)

    def test_full_payment_boundary(self) -> None:
        self.assertIs(derive_fee_status(Decimal("100.00"), Decimal("100.00")), FeeStatus.PAID)
        self.assertIs(derive_fee_status(Decimal("100.00"), Decimal("120.00")), FeeStatus.PAID)

    def test_explicit_status_wins(self) -> None:
        self.assertIs(
            derive_fee_status(Decimal("100.00"), None, FeeStatus.CANCELED), FeeStatus.CANCELED
        )

    def test_negative_amounts_rejected(self) -> None:
        with self.assertRaises(DomainError):
            derive_fee_status(Decimal("-1.00"), None)
        with self.assertRaises(DomainError):
            derive_fee_status(Decimal("1.00"), Decimal("-1.00"))


class DateRulesTest(unittest.TestCase):
    def test_order_rejects_earlier_later(self) -> None:
        with self.assertRaises(DomainError):
            ensure_date_order(datetime.date(2026, 1, 10), datetime.date(2026, 1, 1), "日期顺序错误")

    def test_order_allows_equal_or_empty(self) -> None:
        ensure_date_order(datetime.date(2026, 1, 1), datetime.date(2026, 1, 1), "不成立")
        ensure_date_order(None, datetime.date(2026, 1, 1), "不成立")
        ensure_date_order(datetime.date(2026, 1, 1), None, "不成立")

    def test_due_soon_window_inclusive(self) -> None:
        today = datetime.date(2026, 11, 5)
        self.assertTrue(due_soon_window(today, today, 30))
        self.assertTrue(due_soon_window(today, datetime.date(2026, 12, 5), 30))
        self.assertFalse(due_soon_window(today, datetime.date(2026, 12, 6), 30))
        self.assertFalse(due_soon_window(today, datetime.date(2026, 11, 4), 30))
        self.assertFalse(due_soon_window(today, None, 30))

    def test_invalid_window_rejected(self) -> None:
        with self.assertRaises(DomainError):
            due_soon_window(datetime.date(2026, 11, 5), datetime.date(2026, 11, 6), 0)


class ImportRowTest(unittest.TestCase):
    def test_valid_row_normalized(self) -> None:
        parsed = parse_import_row(
            {"asset_no": " PAT-001 ", "name": " 演示专利 ", "ip_type": "patent", "status_group": ""}
        )
        self.assertNotIn("asset_no", parsed)
        self.assertEqual(parsed["name"], "演示专利")
        self.assertEqual(parsed["ip_type"], "patent")
        self.assertEqual(parsed["status_group"], "in_progress")

    def test_missing_fields_reported_together(self) -> None:
        with self.assertRaises(DomainError) as ctx:
            parse_import_row({"asset_no": "", "name": "", "ip_type": ""})
        self.assertIn("案件名称", str(ctx.exception))

    def test_only_case_name_is_required(self) -> None:
        parsed = parse_import_row({"案件名称": "只有一个名称"})
        self.assertEqual(parsed["name"], "只有一个名称")
        self.assertEqual(parsed["ip_type"], "patent")
        self.assertIsNone(parsed["docket_no"])
        self.assertIsNone(parsed["fee_amount"])

    def test_chinese_columns_are_mapped(self) -> None:
        parsed = parse_import_row(
            {
                "我方文号": " STHL-1 ",
                "申请号": " 202610000001.0 ",
                "案件名称": " 一种测试案件 ",
                "专利所有权人": " 思腾合力 ",
                "官费应缴纳日": "2026-01-01",
                "本次官费缴纳至": "2026/12/31",
                "本次官费缴纳金额": "1,200.00",
                "缴纳日期": "2026年1月5日",
            }
        )
        self.assertEqual(parsed["docket_no"], "STHL-1")
        self.assertEqual(parsed["application_no"], "202610000001.0")
        self.assertEqual(parsed["name"], "一种测试案件")
        self.assertEqual(parsed["patentee"], "思腾合力")
        self.assertEqual(parsed["fee_amount"], Decimal("1200.00"))
        self.assertEqual(parsed["fee_due_date"], datetime.date(2026, 1, 1))
        self.assertEqual(parsed["fee_coverage_end_date"], datetime.date(2026, 12, 31))
        self.assertEqual(parsed["fee_paid_date"], datetime.date(2026, 1, 5))

    def test_invalid_import_date_rejected(self) -> None:
        with self.assertRaises(DomainError) as ctx:
            parse_import_row({"案件名称": "日期错误", "官费应缴纳日": "2026-13-01"})
        self.assertIn("官费应缴纳日", str(ctx.exception))

    def test_unknown_type_and_status(self) -> None:
        with self.assertRaises(DomainError):
            parse_import_row({"asset_no": "A", "name": "B", "ip_type": "unknown"})
        with self.assertRaises(DomainError):
            parse_import_row(
                {"asset_no": "A", "name": "B", "ip_type": "patent", "status_group": "unknown"}
            )

    def test_too_long_fields_rejected(self) -> None:
        with self.assertRaises(DomainError):
            parse_import_row({"name": "B", "ip_type": "patent", "docket_no": "x" * 65})
        with self.assertRaises(DomainError):
            parse_import_row({"name": "n" * 256, "ip_type": "patent"})


class CertificateDatesTest(unittest.TestCase):
    def test_certificate_recipient_order(self) -> None:
        validate_certificate_dates(datetime.date(2026, 1, 1), datetime.date(2026, 1, 2))
        validate_certificate_dates(None, datetime.date(2026, 1, 2))
        with self.assertRaises(DomainError):
            validate_certificate_dates(datetime.date(2026, 1, 5), datetime.date(2026, 1, 1))


class YearGroupingTest(unittest.TestCase):
    def test_groups_sorted_and_ignores_none(self) -> None:
        counts = group_counts_by_year(
            [
                datetime.date(2025, 3, 1),
                datetime.date(2024, 8, 1),
                None,
                datetime.date(2025, 12, 31),
            ]
        )
        self.assertEqual(list(counts.keys()), [2024, 2025])
        self.assertEqual(counts[2025], 2)

    def test_empty_input(self) -> None:
        self.assertEqual(group_counts_by_year([]), {})
        self.assertEqual(group_counts_by_year([None, None]), {})


class UploadValidationTest(unittest.TestCase):
    def test_accepts_supported_suffix_case_insensitively(self) -> None:
        self.assertEqual(validate_upload("a.PDF", "application/pdf", 1024, max_bytes=4096), ".pdf")
        self.assertEqual(
            validate_upload("证书 扫描.JPG", "image/jpeg", 10, max_bytes=4096), ".jpg"
        )

    def test_rejects_missing_name_or_extension(self) -> None:
        with self.assertRaises(DomainError):
            validate_upload("", "application/pdf", 10, max_bytes=4096)
        with self.assertRaises(DomainError):
            validate_upload("README", "text/plain", 10, max_bytes=4096)

    def test_rejects_unknown_suffix(self) -> None:
        with self.assertRaises(DomainError):
            validate_upload("virus.exe", "application/octet-stream", 10, max_bytes=4096)

    def test_rejects_disallowed_mime(self) -> None:
        with self.assertRaises(DomainError):
            validate_upload(
                "a.pdf",
                "application/x-msdownload",
                10,
                max_bytes=4096,
                allowed_mimes=("application/pdf",),
            )

    def test_allows_unknown_mime_when_not_whitelisted(self) -> None:
        self.assertEqual(validate_upload("a.pdf", None, 10, max_bytes=4096), ".pdf")

    def test_size_boundaries(self) -> None:
        self.assertEqual(validate_upload("a.pdf", "application/pdf", 4096, max_bytes=4096), ".pdf")
        with self.assertRaises(DomainError):
            validate_upload("a.pdf", "application/pdf", 4097, max_bytes=4096)
        with self.assertRaises(DomainError):
            validate_upload("a.pdf", "application/pdf", 0, max_bytes=4096)

    def test_invalid_limit_configuration(self) -> None:
        with self.assertRaises(DomainError):
            validate_upload("a.pdf", "application/pdf", 10, max_bytes=0)


class ImportRowsTest(unittest.TestCase):
    def test_mixed_rows_partitioned(self) -> None:
        rows = [
            {"asset_no": "A-1", "name": "甲", "ip_type": "patent"},
            {"asset_no": "A-1", "name": "重复", "ip_type": "patent"},
            {"asset_no": "", "name": "缺号", "ip_type": "patent"},
            {"asset_no": "A-2", "name": "乙", "ip_type": "unknown"},
            {"asset_no": "A-3", "name": "丙", "ip_type": "trademark"},
        ]
        accepted, errors = parse_import_rows(rows)
        # 旧模板的 asset_no 列不再解析，也不参与文件内去重。
        self.assertEqual([item["name"] for item in accepted], ["甲", "重复", "缺号", "丙"])
        self.assertEqual(len(errors), 1)
        # 行号从第 2 行（表头之后）开始，且与原始顺序对应
        self.assertEqual([row for row, _ in errors], [5])

    def test_custom_first_row(self) -> None:
        rows = [{"asset_no": "B-1", "name": "甲", "ip_type": "copyright"}]
        accepted, errors = parse_import_rows(rows, first_data_row=10)
        self.assertEqual(len(accepted), 1)
        self.assertEqual(errors, [])

        _, errors = parse_import_rows([{"asset_no": "", "name": "", "ip_type": ""}], first_data_row=10)
        self.assertEqual(errors[0][0], 10)

    def test_empty_input(self) -> None:
        accepted, errors = parse_import_rows([])
        self.assertEqual(accepted, [])
        self.assertEqual(errors, [])

    def test_valid_rows_are_normalized(self) -> None:
        accepted, _ = parse_import_rows(
            [{"asset_no": " C-1 ", "name": " 丁 ", "ip_type": "patent", "status_group": ""}]
        )
        self.assertEqual(accepted[0]["name"], "丁")
        self.assertEqual(accepted[0]["ip_type"], "patent")
        self.assertEqual(accepted[0]["status_group"], "in_progress")
        self.assertEqual(accepted[0]["_row_number"], 2)


class PercentageTest(unittest.TestCase):
    def test_zero_total_returns_zero(self) -> None:
        self.assertEqual(percentage(0, 0), 0.0)
        self.assertEqual(percentage(5, 0), 0.0)
        self.assertEqual(granted_rate({}, 0), 0.0)

    def test_rounding_to_one_decimal(self) -> None:
        self.assertEqual(percentage(1, 3), 33.3)
        self.assertEqual(percentage(2, 3), 66.7)
        self.assertEqual(percentage(1, 1), 100.0)

    def test_granted_rate_uses_granted_key(self) -> None:
        self.assertEqual(granted_rate({"granted": 3, "in_progress": 1}, 4), 75.0)
        self.assertEqual(granted_rate({"in_progress": 4}, 4), 0.0)

    def test_negative_part_rejected(self) -> None:
        with self.assertRaises(DomainError):
            percentage(-1, 10)


class ParseDecimalTest(unittest.TestCase):
    def test_plain_and_grouped_values(self) -> None:
        self.assertEqual(parse_decimal("8000.00", "金额"), Decimal("8000.00"))
        self.assertEqual(parse_decimal("8,000.50", "金额"), Decimal("8000.50"))
        self.assertIsNone(parse_decimal("", "金额"))
        self.assertIsNone(parse_decimal(None, "金额"))

    def test_rejects_invalid_and_precision(self) -> None:
        with self.assertRaises(DomainError):
            parse_decimal("abc", "金额")
        with self.assertRaises(DomainError):
            parse_decimal("1.234", "金额")
        with self.assertRaises(DomainError):
            parse_decimal("-1.00", "金额")


if __name__ == "__main__":
    unittest.main()
