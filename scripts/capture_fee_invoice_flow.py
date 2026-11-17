"""验证费用台账内的发票入口：点案件名看详情 → 点登记发票弹窗。

    python scripts/capture_fee_invoice_flow.py
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


def main() -> int:
    parser = argparse.ArgumentParser(description="截取费用台账发票入口")
    parser.add_argument("--out", default="docs/screenshot-fees.png")
    parser.add_argument("--out-dialog", default="docs/screenshot-invoice-dialog.png")
    parser.add_argument("--base", default="http://127.0.0.1:5173")
    args = parser.parse_args()

    edge = find_edge()
    if edge is None:
        print("未找到 Edge")
        return 1

    work = pathlib.Path(__file__).resolve().parent.parent / "backend" / "var" / f"fx-{uuid.uuid4().hex[:6]}"
    work.mkdir(parents=True, exist_ok=True)
    port = free_port()
    browser = subprocess.Popen(
        [edge, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
         "--disable-sync", "--disable-extensions", f"--user-data-dir={work/'p'}",
         f"--remote-debugging-port={port}", "--window-size=1440,980", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    cdp = None
    try:
        target = wait_target(port)
        cdp = CDP(target["webSocketDebuggerUrl"])
        cdp.call("Runtime.enable")
        cdp.call("Page.enable")
        cdp.call("Emulation.setDeviceMetricsOverride",
                 {"width": 1440, "height": 980, "deviceScaleFactor": 1, "mobile": False})
        cdp.call("Page.navigate", {"url": f"{args.base}/#/login"})
        time.sleep(2)
        cdp.evaluate(LOGIN)
        time.sleep(2)

        # 1) 确认 /invoices 路由已不存在
        cdp.evaluate("location.hash='#/invoices'")
        time.sleep(2)
        hash_now = cdp.evaluate("location.hash")
        print("访问 #/invoices 后落点:", hash_now)

        # 2) 费用台账：点案件名称打开详情
        cdp.evaluate("location.hash='#/fees'")
        time.sleep(3)
        shot_list = cdp.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
        pathlib.Path(args.out).write_bytes(base64.b64decode(shot_list["data"]))
        print("费用台账截图:", args.out)

        clicked = cdp.evaluate(
            "(()=>{const b=document.querySelector('tbody tr .name-link');"
            "if(!b)return 'none';b.click();return 'clicked'})()"
        )
        print("点击案件名称:", clicked)
        time.sleep(1.5)
        print("详情抽屉:", cdp.evaluate("document.body.innerText.includes('关联发票')"))

        # 3) 点登记发票
        opened = cdp.evaluate(
            "(()=>{const btns=[...document.querySelectorAll('button')];"
            "const b=btns.find(x=>x.textContent.trim()==='登记发票');"
            "if(!b)return 'none';b.click();return 'clicked'})()"
        )
        print("点击登记发票:", opened)
        time.sleep(2)
        print("发票弹窗:", cdp.evaluate("Boolean(document.querySelector('.inv-modal'))"))
        shot_dialog = cdp.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
        pathlib.Path(args.out_dialog).write_bytes(base64.b64decode(shot_dialog["data"]))
        print("弹窗截图:", args.out_dialog)
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
