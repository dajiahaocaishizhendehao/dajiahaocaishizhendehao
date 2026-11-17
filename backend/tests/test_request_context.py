"""请求上下文测试（仅需 starlette，不需要数据库）。

覆盖 client_ip 对 X-Forwarded-For 的解析与回退逻辑，属于审计日志可信度相关代码。

    python -m unittest discover -s backend/tests -t backend -p "test_request_context.py"
"""

from __future__ import annotations

import unittest

try:  # pragma: no cover - 环境相关
    from starlette.requests import Request
except ImportError:  # pragma: no cover
    raise unittest.SkipTest("未安装 starlette，跳过请求上下文测试") from None

from app.request_context import client_ip


def make_request(
    headers: dict[str, str] | None = None,
    client: tuple[str, int] | None = ("10.0.0.8", 1234),
) -> Request:
    raw_headers = [(key.lower().encode(), value.encode()) for key, value in (headers or {}).items()]
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "root_path": "",
        "headers": raw_headers,
        "client": client,
        "server": ("testserver", 80),
    }
    return Request(scope)


class ClientIpTest(unittest.TestCase):
    def test_prefers_first_forwarded_ip(self) -> None:
        request = make_request({"x-forwarded-for": "203.0.113.5, 10.1.1.1"})
        self.assertEqual(client_ip(request), "203.0.113.5")

    def test_strips_spaces(self) -> None:
        self.assertEqual(client_ip(make_request({"x-forwarded-for": "  203.0.113.9  "})), "203.0.113.9")

    def test_falls_back_to_socket_client(self) -> None:
        self.assertEqual(client_ip(make_request()), "10.0.0.8")

    def test_returns_none_without_client(self) -> None:
        self.assertIsNone(client_ip(make_request(client=None)))

    def test_handles_none_request(self) -> None:
        self.assertIsNone(client_ip(None))

    def test_truncates_long_header(self) -> None:
        value = client_ip(make_request({"x-forwarded-for": "9" * 200}))
        self.assertIsNotNone(value)
        self.assertLessEqual(len(value), 64)


if __name__ == "__main__":
    unittest.main()
