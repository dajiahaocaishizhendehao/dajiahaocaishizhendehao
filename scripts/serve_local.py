"""本地静态服务 + /api 反向代理。

用于在没有 npm 的情况下托管 `frontend/dist` 并转发接口请求，
让浏览器能以同源方式访问后端。

用法：
    python scripts/serve_local.py --dir frontend/dist --port 5173 --api http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import functools
import http.server
import pathlib
import urllib.error
import urllib.request


class Handler(http.server.SimpleHTTPRequestHandler):
    api_base = "http://127.0.0.1:8000"

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        # 只记录接口错误，避免静态资源刷屏。
        if self.path.startswith("/api/"):
            super().log_message(format, *args)

    def _proxy(self) -> None:
        length = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(length) if length else None
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() in {"authorization", "content-type", "accept"}
        }
        request = urllib.request.Request(
            f"{self.api_base}{self.path}", data=body, method=self.command, headers=headers
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = response.read()
                self.send_response(response.status)
                self.send_header("Content-Type", response.headers.get("Content-Type", "application/json"))
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
        except urllib.error.HTTPError as error:
            payload = error.read()
            self.send_response(error.code)
            self.send_header("Content-Type", error.headers.get("Content-Type", "application/json"))
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except urllib.error.URLError as error:
            message = f'{{"detail":"后端不可用：{error.reason}"}}'.encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(message)))
            self.end_headers()
            self.wfile.write(message)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/api/"):
            self._proxy()
        else:
            super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        self._proxy()

    def do_PATCH(self) -> None:  # noqa: N802
        self._proxy()

    def do_PUT(self) -> None:  # noqa: N802
        self._proxy()

    def do_DELETE(self) -> None:  # noqa: N802
        self._proxy()


def main() -> int:
    parser = argparse.ArgumentParser(description="本地前端静态服务（带接口代理）")
    parser.add_argument("--dir", default="frontend/dist")
    parser.add_argument("--port", type=int, default=5173)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    directory = pathlib.Path(args.dir).resolve()
    if not (directory / "index.html").exists():
        print(f"未找到构建产物：{directory}/index.html，请先执行 vite build。")
        return 1

    Handler.api_base = args.api.rstrip("/")
    handler = functools.partial(Handler, directory=str(directory))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"前端已启动：http://127.0.0.1:{args.port}  （/api → {Handler.api_base}）")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
