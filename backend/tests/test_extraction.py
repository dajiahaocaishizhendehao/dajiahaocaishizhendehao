"""证书文本解析测试（纯函数，不需要 OCR 引擎）。

样例文本取自真实「专利登记簿副本」的 OCR 结果（含识别噪声）。

    python -m unittest discover -s backend/tests -t backend -p "test_extraction.py"
"""

from __future__ import annotations

import unittest

from app.extraction import parse_certificate

SAMPLE = """囤  家  知  识  产  权  局 | NATIONAL INTELLECTUAL PROPERTY
专利登记簿副本
专利号:U201510859494.3
证书号:2775265
著录项目
名  称:
一种眼底图像对比度增强方法
2015年11月27日
分  类
G06T 5/00(2006.01)
明  人:
肖志涛。张欣鹏。耿磊。张芳。吴骏
专利权人:思腾合力(天津)科技有限公司
专利权人地址:天津经济技术开发区逸仙科学工业园翠浦道1号
专利权人邮政编码:300450
法律状态
专利权有效
授权公告日:2018年01月12日
"""


class ParseCertificateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fields, self.warnings = parse_certificate(SAMPLE)

    def test_patent_no_cleaned(self) -> None:
        self.assertEqual(self.fields.get("patent_no"), "201510859494.3")

    def test_certificate_no(self) -> None:
        self.assertEqual(self.fields.get("certificate_no"), "2775265")

    def test_name(self) -> None:
        self.assertEqual(self.fields.get("name"), "一种眼底图像对比度增强方法")

    def test_dates(self) -> None:
        self.assertEqual(self.fields.get("application_date"), "2015-11-27")
        self.assertEqual(self.fields.get("grant_date"), "2018-01-12")

    def test_patentee_and_status(self) -> None:
        self.assertIn("思腾合力", self.fields.get("patentee", ""))
        self.assertEqual(self.fields.get("legal_status"), "专利权有效")

    def test_inventors_separators_normalized(self) -> None:
        inventors = self.fields.get("inventors", "")
        self.assertIn("肖志涛", inventors)
        self.assertNotIn("。", inventors)

    def test_no_warnings_when_key_fields_found(self) -> None:
        self.assertEqual(self.warnings, [])


class ParseEmptyTest(unittest.TestCase):
    def test_missing_fields_produce_warnings(self) -> None:
        fields, warnings = parse_certificate("完全无关的文字")
        self.assertEqual(fields, {})
        self.assertEqual(len(warnings), 2)

    def test_invalid_date_ignored(self) -> None:
        fields, _ = parse_certificate("申请日:2015年13月45日 专利号:2015108594943")
        self.assertNotIn("application_date", fields)


if __name__ == "__main__":
    unittest.main()
