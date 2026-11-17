"""在材料中心演示模糊选案件：输入关键字并截取下拉结果。

    python scripts/capture_picker.py --out docs/screenshot-picker.png --keyword 眼底
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

LOGIN = (
    "(()=>{const s=(q,v)=>{const e=document.querySelector(q);"
    "if(!e)return false;e.value=v;e.dispatchEvent(new Event('input',{bubbles:true}));return true};"
    "s('#username','admin');s('#password','Admin@12345');"
    "document.querySelector('form.login-card button').click();return 'ok'})()"
)

TYPE_KEYWORD = """
(() => {
  const input = document.querySelector('.picker-input');
  if (!input) return 'no-input';
  input.dispatchEvent(new FocusEvent('focus'));
  input.focus();
  input.value = '%s';
  input.dispatchEvent(new Event('input', { bubbles: true }));
  return 'typed';
})()
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="截取案件模糊搜索")
    parser.add_argument("--out", default="docs/screenshot-picker.png")
    parser.add_argument("--base", default="http://127.0.0.1:5173")
    parser.add_argument("--keyword", default="眼底")
    args = parser.parse_args()

    edge = find_edge()
    if edge is None:
        print("未找到 Microsoft Edge。")
        return 1

    work = pathlib.Path(__file__).resolve().parent.parent / "backend" / "var" / f"pick-{uuid.uuid4().hex[:6]}"
    work.mkdir(parents=True, exist_ok=True)
    port = free_port()
    browser = subprocess.Popen(
        [
            edge,
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-sync",
            "--disable-extensions",
            f"--user-data-dir={work / 'profile'}",
            f"--remote-debugging-port={port}",
            "--window-size=1440,900",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    cdp = None
    try:
        target = wait_target(port)
        cdp = CDP(target["webSocketDebuggerUrl"])
        cdp.call("Runtime.enable")
        cdp.call("Page.enable")
        cdp.call(
            "Emulation.setDeviceMetricsOverride",
            {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False},
        )
        cdp.call("Page.navigate", {"url": f"{args.base}/#/login"})
        time.sleep(2)
        cdp.evaluate(LOGIN)
        time.sleep(2)
        cdp.evaluate("location.hash='#/materials'")
        time.sleep(3)

        print("输入关键字：", cdp.evaluate(TYPE_KEYWORD % args.keyword))
        time.sleep(1)
        count = cdp.evaluate("document.querySelectorAll('.picker-option').length")
        print("匹配条数：", count)
        print(
            "调试：",
            cdp.evaluate(
                "JSON.stringify({input: document.querySelector('.picker-input')?.value ?? null, "
                "list: Boolean(document.querySelector('.picker-list')), "
                "empty: Boolean(document.querySelector('.picker-empty')), "
                "options: document.querySelectorAll('.picker-option').length, "
                "rows: document.querySelectorAll('tbody tr').length})"
            ),
        )

        shot = cdp.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
        out = pathlib.Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(base64.b64decode(shot["data"]))
        print(f"已保存：{out}（{out.stat().st_size} 字节）")
        return 0 if int(count or 0) > 0 else 2
    finally:
        if cdp is not None:
            cdp.close()
        browser.terminate()
        try:
            browser.wait(timeout=10)
        except subprocess.TimeoutExpired:
            browser.kill()
        for path in sorted(work.rglob("*"), reverse=True):
            try:
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            except OSError:
                pass
        try:
            work.rmdir()
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
