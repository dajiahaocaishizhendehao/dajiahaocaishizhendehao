"""电子发票布局解析与专利 OCR 抗噪测试。"""
from __future__ import annotations

import unittest

from app.extraction import parse_certificate, parse_invoice, parse_invoice_layout


class InvoiceLayoutTest(unittest.TestCase):
    def test_tax_invoice_words(self) -> None:
        words = [
            (438, 32, 480, 40, "发票号码："), (482, 32, 570, 40, "26332000008369951806"),
            (438, 49, 480, 57, "开票日期："), (482, 49, 550, 57, "2026年09月28日"),
            (32, 96, 55, 104, "名称："), (57, 96, 250, 104, "北京清枢智汇科技有限公司"),
            (317, 96, 339, 104, "名称："), (340, 96, 550, 104, "杭州深度求索人工智能基础技术研究有限公司"),
            (392, 259, 440, 269, "¥943.40"), (544, 259, 590, 269, "¥56.60"),
            (407, 280, 438, 288, "（小写）"), (439, 278, 500, 288, "¥1000.00"),
        ]
        fields, warnings = parse_invoice_layout(words)
        self.assertEqual(fields["invoice_no"], "26332000008369951806")
        self.assertEqual(fields["invoice_date"], "2026-09-28")
        self.assertEqual(fields["buyer"], "北京清枢智汇科技有限公司")
        self.assertEqual(fields["seller"], "杭州深度求索人工智能基础技术研究有限公司")
        self.assertEqual(fields["amount_net"], "943.40")
        self.assertEqual(fields["tax_amount"], "56.60")
        self.assertEqual(fields["amount_gross"], "1000.00")
        self.assertEqual(warnings, [])

    def test_non_invoice_warning(self) -> None:
        fields, warnings = parse_invoice("LDZD-1A 流动终端技术规格书\n范围\n技术要求")
        self.assertEqual(fields, {})
        self.assertEqual(warnings, ["文件内容疑似不是发票，请确认上传文件"])


class PatentNoiseTest(unittest.TestCase):
    def test_registry_copy_ocr_noise(self) -> None:
        text = """专利登记簿副本
专利号:兀201510859494.3
证书号:2775265
I 著录项目
一种眼底图像对比度增强方法
2015年11月27日
专利权人:思腾合力(天津)科技有限公司
工法律状态
专利权有效
授权公告日:2018年01月12日
原专利权人名称:天津工业大学
"""
        fields, warnings = parse_certificate(text)
        self.assertEqual(fields["patent_no"], "201510859494.3")
        self.assertEqual(fields["name"], "一种眼底图像对比度增强方法")
        self.assertEqual(fields["application_date"], "2015-11-27")
        self.assertEqual(fields["grant_date"], "2018-01-12")
        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
