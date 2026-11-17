"""浏览器渲染验证：真实后端 + 真实前端产物 + 无头浏览器。

不依赖 Playwright/Puppeteer，也不需要 npm 运行时：

1. 以子进程启动 uvicorn（SQLite 临时库）；
2. 进程内起一个静态服务器，托管 `frontend/dist` 并把 `/api/*` 代理到后端；
3. 通过 HTTP 登录取得令牌；
4. 生成一个测试页，在应用启动前把令牌写入 localStorage；
5. 用无头 Edge 打开不同路由并导出 DOM，断言页面渲染出预期内容；
6. 关闭服务、清理临时文件。

前提：已执行过 `vite build` 生成 `frontend/dist`；Edge 可在当前权限下启动。

用法：
    python scripts/browser_check.py
"""

from __future__ import annotations

import http.server
import json
import os
import pathlib
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

ROOT = pathlib.Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
DIST = ROOT / "frontend" / "dist"

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

failures: list[str] = []
checks = 0


def check(condition: bool, message: str) -> None:
    global checks
    checks += 1
    if condition:
        print(f"ok   {message}")
    else:
        failures.append(message)
        print(f"FAIL {message}")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def find_edge() -> str | None:
    for path in EDGE_CANDIDATES:
        if pathlib.Path(path).exists():
            return path
    return None


def seed_database(db_url: str) -> None:
    os.environ["DATABASE_URL"] = db_url
    sys.path.insert(0, str(BACKEND))

    from app import security
    from app.database import Base, SessionLocal, get_engine
    from app.models import User, UserRole

    engine = get_engine()
    Base.metadata.create_all(engine)
    with SessionLocal(bind=engine) as db:
        db.add(
            User(
                username="admin",
                display_name="管理员",
                password_hash=security.hash_password("Passw0rd!"),
                role=UserRole.ADMIN,
            )
        )
        db.commit()
    engine.dispose()


class SPAHandler(http.server.SimpleHTTPRequestHandler):
    """静态文件 + /api 反向代理。"""

    backend_base = "http://127.0.0.1:8000"

    def __init__(self, *args, directory: str | None = None, **kwargs):  # noqa: D107
        super().__init__(*args, directory=directory, **kwargs)

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        pass

    def _proxy(self) -> None:
        length = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(length) if length else None
        request = urllib.request.Request(
            f"{self.backend_base}{self.path}",
            data=body,
            method=self.command,
            headers={
                key: value
                for key, value in self.headers.items()
                if key.lower() in {"authorization", "content-type", "accept"}
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = response.read()
                self.send_response(response.status)
                for key, value in response.headers.items():
                    if key.lower() in {"content-type", "content-length"}:
                        continue
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

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/api/"):
            self._proxy()
        else:
            super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        self._proxy()

    def do_PATCH(self) -> None:  # noqa: N802
        self._proxy()

    def do_DELETE(self) -> None:  # noqa: N802
        self._proxy()


def build_bootstrap_page(token: str) -> str:
    """复制 index.html，并在应用脚本之前写入令牌。"""

    index = (DIST / "index.html").read_text(encoding="utf-8")
    injection = (
        "<script>try{localStorage.setItem('ipms_token', "
        + json.dumps(token)
        + ");}catch(e){}</script>"
    )
    return index.replace("<script type=\"module\"", injection + "<script type=\"module\"", 1)


def dump_dom(edge: str, url: str, profile: pathlib.Path, workdir: pathlib.Path, label: str) -> str:
    out = workdir / f"{label}.html"
    err = workdir / f"{label}.err"
    process = subprocess.run(
        [
            edge,
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            f"--user-data-dir={profile}",
            "--virtual-time-budget=8000",
            "--dump-dom",
            url,
        ],
        capture_output=True,
        text=False,
        timeout=120,
    )
    out.write_bytes(process.stdout or b"")
    err.write_bytes(process.stderr or b"")
    return (process.stdout or b"").decode("utf-8", errors="replace")


def main() -> int:
    if not (DIST / "index.html").exists():
        print("跳过：未找到 frontend/dist，请先执行 vite build。")
        return 0

    edge = find_edge()
    if edge is None:
        print("跳过：未找到 Microsoft Edge。")
        return 0

    workdir = BACKEND / "var" / f"browser-check-{uuid.uuid4().hex[:8]}"
    workdir.mkdir(parents=True, exist_ok=True)
    db_url = f"sqlite+pysqlite:///{(workdir / 'ipms.db').as_posix()}"
    seed_database(db_url)

    api_port = free_port()
    SPAHandler.backend_base = f"http://127.0.0.1:{api_port}"
    env = dict(os.environ)
    env["DATABASE_URL"] = db_url
    env["PYTHONPATH"] = os.pathsep.join([str(BACKEND), env.get("PYTHONPATH", "")]).strip(os.pathsep)

    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(api_port),
            "--log-level",
            "warning",
        ],
        cwd=str(BACKEND),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    httpd = None
    try:
        deadline = time.time() + 40
        ready = False
        while time.time() < deadline:
            try:
                request = urllib.request.Request(f"{SPAHandler.backend_base}/health")
                with urllib.request.urlopen(request, timeout=3) as response:
                    ready = response.status == 200
                    if ready:
                        break
            except OSError:
                time.sleep(0.4)
        check(ready, "后端服务就绪")

        status, payload = _login(SPAHandler.backend_base)
        token = payload.get("access_token") if isinstance(payload, dict) else None
        check(status == 200 and bool(token), f"登录取得令牌（HTTP {status}）")

        (DIST / "_e2e.html").write_text(build_bootstrap_page(token or ""), encoding="utf-8")

        spa_port = free_port()
        handler = lambda *args, **kwargs: SPAHandler(*args, directory=str(DIST), **kwargs)  # noqa: E731
        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", spa_port), handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()

        base = f"http://127.0.0.1:{spa_port}"
        profile = workdir / "edge-profile"

        pages = [
            ("dashboard", f"{base}/_e2e.html#/", ["知识产权工作台", "全部档案", "待处理事项", "缺少发票费用"]),
            ("materials", f"{base}/_e2e.html#/materials", ["材料中心", "上传材料"]),
            ("dates", f"{base}/_e2e.html#/dates", ["日期台账", "不构成法律建议"]),
        ]

        for label, url, markers in pages:
            dom = dump_dom(edge, url, profile, workdir, label)
            rendered = 'data-v-app' in dom
            check(rendered, f"{label}: Vue 已挂载")
            for marker in markers:
                check(marker in dom, f"{label}: 渲染出「{marker}」")

        # 未登录访问应被路由守卫挡回登录页
        anon = dump_dom(edge, f"{base}/index.html#/", workdir / "edge-anon", workdir, "anonymous")
        check("login-card" in anon, "匿名访问被重定向到登录页")

    finally:
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        (DIST / "_e2e.html").unlink(missing_ok=True)
        for path in sorted(workdir.rglob("*"), reverse=True):
            try:
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            except OSError:
                pass
        try:
            workdir.rmdir()
        except OSError:
            pass

    print()
    if failures:
        print(f"浏览器验证失败 {len(failures)} 项 / 共 {checks} 项：")
        for item in failures:
            print(f" - {item}")
        return 1

    print(f"浏览器验证全部通过（{checks} 项检查）。")
    return 0


def _login(base: str) -> tuple[int, dict]:
    data = json.dumps({"username": "admin", "password": "Passw0rd!"}).encode()
    request = urllib.request.Request(
        f"{base}/api/auth/login", data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        return error.code, {}


if __name__ == "__main__":
    raise SystemExit(main())
