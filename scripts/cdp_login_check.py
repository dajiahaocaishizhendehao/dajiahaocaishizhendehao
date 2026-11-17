"""浏览器交互验证：真实填写登录表单并跳转到工作台。

不依赖 Playwright：用标准库实现一个最小 WebSocket 客户端，直接驱动
Edge 的 Chrome DevTools Protocol（CDP）。

流程：
1. 启动 uvicorn（SQLite 临时库，写入管理员账号）；
2. 进程内托管 dist 并代理 /api；
3. 启动带 --remote-debugging-port 的无头 Edge；
4. 通过 CDP 打开页面、填入账号密码、点击登录；
5. 轮询页面状态，确认跳转到工作台并渲染出接口数据；
6. 关闭进程、清理临时文件。

用法（需要完整权限，浏览器进程无法在受限沙箱启动）：
    python scripts/cdp_login_check.py
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import pathlib
import socket
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

SCRIPTS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from browser_check import (  # noqa: E402
    BACKEND,
    DIST,
    SPAHandler,
    find_edge,
    free_port,
    seed_database,
)

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


class WebSocket:
    """最小 WebSocket 客户端，只支持文本帧与 ping/pong。"""

    def __init__(self, url: str, timeout: float = 30.0) -> None:
        assert url.startswith("ws://"), url
        rest = url[len("ws://") :]
        host_port, path = rest.split("/", 1)
        host, port_text = host_port.split(":")
        self.sock = socket.create_connection((host, int(port_text)), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        handshake = (
            f"GET /{path} HTTP/1.1\r\n"
            f"Host: {host}:{port_text}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(handshake.encode())
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("WebSocket 握手失败：连接被关闭")
            response += chunk
        if b"101" not in response.split(b"\r\n", 1)[0]:
            raise ConnectionError(f"WebSocket 握手失败：{response.split(b'\r\n', 1)[0]!r}")

    def send(self, text: str) -> None:
        payload = text.encode("utf-8")
        header = bytearray([0x81])  # FIN + text
        mask = os.urandom(4)
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header += struct.pack(">H", length)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", length)
        header += mask
        masked = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def _read_exact(self, size: int) -> bytes:
        buffer = b""
        while len(buffer) < size:
            chunk = self.sock.recv(size - len(buffer))
            if not chunk:
                raise ConnectionError("WebSocket 连接已关闭")
            buffer += chunk
        return buffer

    def recv(self) -> str:
        while True:
            first = self._read_exact(2)
            opcode = first[0] & 0x0F
            masked = bool(first[1] & 0x80)
            length = first[1] & 0x7F
            if length == 126:
                length = struct.unpack(">H", self._read_exact(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", self._read_exact(8))[0]
            mask = self._read_exact(4) if masked else None
            payload = self._read_exact(length) if length else b""
            if mask:
                payload = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
            if opcode == 0x8:
                raise ConnectionError("WebSocket 被关闭")
            if opcode == 0x9:  # ping
                self._send_pong(payload)
                continue
            if opcode in (0x1, 0x2):
                return payload.decode("utf-8", errors="replace")

    def _send_pong(self, payload: bytes) -> None:
        frame = bytearray([0x8A, 0x80 | len(payload)])
        mask = os.urandom(4)
        frame += mask
        frame += bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
        self.sock.sendall(bytes(frame))

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


class CDP:
    def __init__(self, ws_url: str) -> None:
        self.ws = WebSocket(ws_url)
        self.next_id = 0
        self.events: list[dict] = []

    def call(self, method: str, params: dict | None = None, timeout: float = 30.0) -> dict:
        self.next_id += 1
        message_id = self.next_id
        self.ws.send(json.dumps({"id": message_id, "method": method, "params": params or {}}))
        deadline = time.time() + timeout
        while time.time() < deadline:
            message = json.loads(self.ws.recv())
            if message.get("id") == message_id:
                if "error" in message:
                    raise RuntimeError(f"{method} 失败：{message['error']}")
                return message.get("result", {})
            if "method" in message:
                self.events.append(message)
        raise TimeoutError(f"{method} 超时")

    def evaluate(self, expression: str) -> str:
        result = self.call(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
        )
        value = result.get("result", {}).get("value")
        return "" if value is None else str(value)

    def close(self) -> None:
        self.ws.close()


def wait_target(debug_port: int, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{debug_port}/json/list", timeout=3) as response:
                targets = json.loads(response.read().decode())
            for target in targets:
                if target.get("type") == "page" and target.get("webSocketDebuggerUrl"):
                    return target
        except (OSError, json.JSONDecodeError):
            pass
        time.sleep(0.4)
    raise TimeoutError("未找到可调试的页面目标")


LOGIN_SCRIPT = r"""
(() => {
  const setValue = (selector, value) => {
    const el = document.querySelector(selector);
    if (!el) return false;
    el.value = value;
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  };
  const okUser = setValue('#username', 'admin');
  const okPass = setValue('#password', 'Passw0rd!');
  const button = document.querySelector('form.login-card button');
  if (button) button.click();
  return JSON.stringify({ okUser, okPass, clicked: Boolean(button) });
})()
"""


def main() -> int:
    if not (DIST / "index.html").exists():
        print("跳过：未找到 frontend/dist，请先执行 vite build。")
        return 0

    edge = find_edge()
    if edge is None:
        print("跳过：未找到 Microsoft Edge。")
        return 0

    workdir = BACKEND / "var" / f"cdp-check-{uuid.uuid4().hex[:8]}"
    workdir.mkdir(parents=True, exist_ok=True)
    db_url = f"sqlite+pysqlite:///{(workdir / 'ipms.db').as_posix()}"
    seed_database(db_url)

    api_port = free_port()
    SPAHandler.backend_base = f"http://127.0.0.1:{api_port}"
    env = dict(os.environ)
    env["DATABASE_URL"] = db_url
    env["PYTHONPATH"] = os.pathsep.join([str(BACKEND), env.get("PYTHONPATH", "")]).strip(os.pathsep)

    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(api_port), "--log-level", "warning"],
        cwd=str(BACKEND),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    spa_port = free_port()
    handler = lambda *args, **kwargs: SPAHandler(*args, directory=str(DIST), **kwargs)  # noqa: E731
    httpd = threading_http = None
    import http.server

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", spa_port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{spa_port}"

    debug_port = free_port()
    browser = subprocess.Popen(
        [
            edge,
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-sync",
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-features=msEdgeSyncPromo,msImplicitSignin,EdgeCollections",
            f"--user-data-dir={workdir / 'edge-profile'}",
            f"--remote-debugging-port={debug_port}",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    cdp = None
    try:
        deadline = time.time() + 40
        ready = False
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"{SPAHandler.backend_base}/health", timeout=3) as response:
                    if response.status == 200:
                        ready = True
                        break
            except OSError:
                time.sleep(0.4)
        check(ready, "后端服务就绪")

        target = wait_target(debug_port)
        cdp = CDP(target["webSocketDebuggerUrl"])
        cdp.call("Runtime.enable")
        cdp.call("Page.enable")

        # 用 CDP 导航，避免 Edge 首次启动页覆盖目标地址。
        cdp.call("Page.navigate", {"url": f"{base}/index.html#/login"})
        time.sleep(2)

        # 等待登录页渲染完成
        rendered = ""
        deadline = time.time() + 20
        while time.time() < deadline:
            rendered = cdp.evaluate("document.querySelector('form.login-card') ? 'ready' : 'no'")
            if rendered == "ready":
                break
            time.sleep(0.3)
        check(rendered == "ready", "登录页已渲染")

        before = cdp.evaluate("location.hash + '|' + document.title")
        check("#/login" in before, f"初始位于登录页（{before}）")

        outcome = cdp.evaluate(LOGIN_SCRIPT)
        payload = json.loads(outcome) if outcome.startswith("{") else {}
        check(payload.get("okUser") is True and payload.get("okPass") is True, "账号与密码已填入表单")
        check(payload.get("clicked") is True, "点击了登录按钮")

        # 等待跳转并渲染工作台
        hash_value = ""
        body = ""
        deadline = time.time() + 25
        while time.time() < deadline:
            hash_value = cdp.evaluate("location.hash")
            body = cdp.evaluate("document.body.innerText")
            if "知识产权工作台" in body:
                break
            time.sleep(0.5)

        check(hash_value in ("#/", "#"), f"登录后跳转到工作台（{hash_value}）")
        check("知识产权工作台" in body, "工作台渲染完成")
        check("全部档案" in body and "待处理事项" in body, "工作台展示了实用指标与待办")
        check("登录" not in body.split("工作台")[0][:40], "登录表单已被替换")

        # 会话保持：刷新后仍是登录态
        cdp.call("Page.reload", {"ignoreCache": False})
        time.sleep(3)
        after_reload = cdp.evaluate("document.body.innerText")
        check("知识产权工作台" in after_reload, "刷新后仍保持登录态")

    finally:
        if cdp is not None:
            cdp.close()
        browser.terminate()
        try:
            browser.wait(timeout=10)
        except subprocess.TimeoutExpired:
            browser.kill()
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
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
        print(f"浏览器交互验证失败 {len(failures)} 项 / 共 {checks} 项：")
        for item in failures:
            print(f" - {item}")
        return 1

    print(f"浏览器交互验证全部通过（{checks} 项检查）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
