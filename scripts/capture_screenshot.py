"""对已运行的本地实例截取页面截图。

前提：`python scripts/run_local.py` 已启动（前端 5173、后端 8000），
且本机存在 Microsoft Edge。

用法：
    python scripts/capture_screenshot.py --url http://127.0.0.1:5173/#/login --out docs/screenshot-dashboard.png
"""

from __future__ import annotations

import argparse
import base64
import pathlib
import subprocess
import sys
import time
import uuid

SCRIPTS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from cdp_login_check import CDP, find_edge, free_port, wait_target  # noqa: E402

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
  setValue('#username', 'admin');
  setValue('#password', 'admin');
  const button = document.querySelector('form.login-card button');
  if (button) button.click();
  return 'ok';
})()
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="截取本地实例页面")
    parser.add_argument("--url", default="http://127.0.0.1:5173/#/login")
    parser.add_argument("--out", default="docs/screenshot-dashboard.png")
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=1000)
    parser.add_argument("--expect", default="知识产权工作台", help="登录后等待出现的文本")
    parser.add_argument("--click-tab", type=int, default=None, help="点击第 N 个页签（从 0 开始）")
    args = parser.parse_args()

    edge = find_edge()
    if edge is None:
        print("未找到 Microsoft Edge。")
        return 1

    workdir = pathlib.Path(__file__).resolve().parent.parent / "backend" / "var" / f"shot-{uuid.uuid4().hex[:8]}"
    workdir.mkdir(parents=True, exist_ok=True)
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
            "--disable-features=msEdgeSyncPromo,msImplicitSignin",
            f"--user-data-dir={workdir / 'profile'}",
            f"--remote-debugging-port={debug_port}",
            f"--window-size={args.width},{args.height}",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    cdp = None
    try:
        target = wait_target(debug_port)
        cdp = CDP(target["webSocketDebuggerUrl"])
        cdp.call("Runtime.enable")
        cdp.call("Page.enable")
        cdp.call(
            "Emulation.setDeviceMetricsOverride",
            {"width": args.width, "height": args.height, "deviceScaleFactor": 1, "mobile": False},
        )
        cdp.call("Page.navigate", {"url": args.url})
        time.sleep(2)

        # 只要出现登录表单就先登录（目标页面可能是任意受保护路由）。
        deadline = time.time() + 25
        login_ok = False
        while time.time() < deadline:
            state = cdp.evaluate(
                "document.querySelector('form.login-card') ? 'login' : (document.querySelector('.app-shell') ? 'app' : 'loading')"
            )
            if state == "login":
                cdp.evaluate(LOGIN_SCRIPT)
                time.sleep(1.5)
                after = cdp.evaluate(
                    "document.querySelector('form.login-card') ? 'login' : 'app'"
                )
                login_ok = after == "app"
                break
            if state == "app":
                login_ok = True
                break
            time.sleep(0.4)

        if not login_ok:
            print("登录未成功，页面：", cdp.evaluate("document.body.innerText.slice(0, 120).replace(/\\n/g, ' ')"))

        # 登录成功后切到目标路由
        target_hash = args.url.split("#", 1)[1] if "#" in args.url else ""
        if target_hash and not target_hash.startswith("/login"):
            cdp.evaluate(f"location.hash = '#{target_hash}'")
            deadline = time.time() + 16
            while time.time() < deadline:
                if args.expect in cdp.evaluate("document.body.innerText"):
                    break
                time.sleep(0.4)
        time.sleep(1)

        if args.click_tab is not None:
            cdp.evaluate(
                "(() => { const tabs = document.querySelectorAll('.tab'); "
                f"if (tabs[{args.click_tab}]) tabs[{args.click_tab}].click(); return 'ok'; }})()"
            )
            time.sleep(1)

        detail = cdp.evaluate("location.hash + ' || ' + document.body.innerText.slice(0, 80).replace(/\\n/g, ' ')")
        print(f"页面状态：{detail}")
        print("期望文本存在：", args.expect in cdp.evaluate("document.body.innerText"))

        shot = cdp.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
        data = shot.get("data")
        if not data:
            print("截图失败：未返回数据")
            return 1

        out = pathlib.Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(base64.b64decode(data))
        title = cdp.evaluate("document.title")
        print(f"已保存截图：{out}（{out.stat().st_size} 字节，标题：{title}）")
        return 0
    finally:
        if cdp is not None:
            cdp.close()
        browser.terminate()
        try:
            browser.wait(timeout=10)
        except subprocess.TimeoutExpired:
            browser.kill()
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


if __name__ == "__main__":
    raise SystemExit(main())
