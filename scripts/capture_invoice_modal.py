"""截取新版登记发票弹窗（左原件 + 右确认）。

    python scripts/capture_invoice_modal.py --out docs/screenshot-invoice-modal.png
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

OPEN_MODAL = (
    "(()=>{const buttons=[...document.querySelectorAll('button')];"
    "const b=buttons.find(x=>x.textContent.trim().includes('登记发票'));"
    "if(!b)return 'none';b.click();return 'clicked'})()"
)


def main() -> int:
    parser = argparse.ArgumentParser(description="截取登记发票弹窗")
    parser.add_argument("--out", default="docs/screenshot-invoice-modal.png")
    parser.add_argument("--base", default="http://127.0.0.1:5173")
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=980)
    args = parser.parse_args()

    edge = find_edge()
    if edge is None:
        print("未找到 Edge")
        return 1

    work = pathlib.Path(__file__).resolve().parent.parent / "backend" / "var" / f"inv2-{uuid.uuid4().hex[:6]}"
    work.mkdir(parents=True, exist_ok=True)
    port = free_port()
    browser = subprocess.Popen(
        [edge, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
         "--disable-sync", "--disable-extensions", f"--user-data-dir={work/'p'}",
         f"--remote-debugging-port={port}", f"--window-size={args.width},{args.height}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    cdp = None
    try:
        target = wait_target(port)
        cdp = CDP(target["webSocketDebuggerUrl"])
        cdp.call("Runtime.enable")
        cdp.call("Page.enable")
        cdp.call("Emulation.setDeviceMetricsOverride",
                 {"width": args.width, "height": args.height, "deviceScaleFactor": 1, "mobile": False})
        cdp.call("Page.navigate", {"url": f"{args.base}/#/login"})
        time.sleep(2)
        cdp.evaluate(LOGIN)
        time.sleep(2)
        cdp.evaluate("location.hash='#/invoices'")
        time.sleep(3)
        print("打开弹窗：", cdp.evaluate(OPEN_MODAL))
        time.sleep(1.5)
        print("弹窗存在：", cdp.evaluate("Boolean(document.querySelector('.inv-modal'))"))
        shot = cdp.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
        out = pathlib.Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(base64.b64decode(shot["data"]))
        print(f"已保存：{out}（{out.stat().st_size} 字节）")
        return 0
    finally:
        if cdp:
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
