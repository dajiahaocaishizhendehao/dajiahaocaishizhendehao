"""增值税发票文本解析测试（纯函数，不需要 OCR）。

    python -m unittest discover -s backend/tests -t backend -p "test_invoice_parse.py"
"""

from __future__ import annotations

import unittest

from app.extraction import parse_invoice

SAMPLE = """
电子发票（增值税专用发票）
发票代码：011002300111
发票号码：26312000000123456
开票日期：2026年03月18日
购买方信息
名 称：思腾合力（天津）科技有限公司
销售方信息
名 称：北京示例知识产权代理有限公司
项目名称 规格型号 单位 数量 单价 金额 税率 税额
*鉴证咨询服务*专利代理费 1 943.40 6% 56.60
合 计 ¥943.40 ¥56.60
价税合计（大写）壹仟圆整 （小写）¥1,000.00
"""


class ParseInvoiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fields, self.warnings = parse_invoice(SAMPLE)

    def test_invoice_number(self) -> None:
        self.assertEqual(self.fields.get("invoice_no"), "26312000000123456")

    def test_invoice_code(self) -> None:
        self.assertEqual(self.fields.get("invoice_code"), "011002300111")

    def test_invoice_date(self) -> None:
        self.assertEqual(self.fields.get("invoice_date"), "2026-03-18")

    def test_amounts(self) -> None:
        self.assertEqual(self.fields.get("amount_net"), "943.40")
        self.assertEqual(self.fields.get("tax_amount"), "56.60")
        self.assertEqual(self.fields.get("amount_gross"), "1000.00")

    def test_parties(self) -> None:
        self.assertIn("思腾合力", self.fields.get("buyer", ""))
        self.assertIn("示例知识产权", self.fields.get("seller", ""))

    def test_no_warnings(self) -> None:
        self.assertEqual(self.warnings, [])


class ParseInvoiceEmptyTest(unittest.TestCase):
    def test_missing_fields_warn(self) -> None:
        fields, warnings = parse_invoice("一些无关的文字")
        self.assertEqual(fields, {})
        self.assertEqual(warnings, ["文件内容疑似不是发票，请确认上传文件"])

    def test_invalid_date_warns(self) -> None:
        fields, warnings = parse_invoice("发票号码：12345678 开票日期：2026年13月40日 价税合计 ¥10.00")
        self.assertNotIn("invoice_date", fields)
        self.assertTrue(any("日期" in item for item in warnings))


if __name__ == "__main__":
    unittest.main()
