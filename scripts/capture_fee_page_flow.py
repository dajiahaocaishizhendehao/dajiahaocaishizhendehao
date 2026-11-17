"""验证费用详情页：#/fees → 点案件名称 → 详情页（非弹窗）→ 登记发票弹窗。

    python scripts/capture_fee_page_flow.py
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
    parser = argparse.ArgumentParser(description="验证费用详情页")
    parser.add_argument("--out-detail", default="docs/screenshot-fee-detail.png")
    parser.add_argument("--out-list", default="docs/screenshot-fees.png")
    parser.add_argument("--base", default="http://127.0.0.1:5173")
    args = parser.parse_args()

    edge = find_edge()
    if edge is None:
        print("未找到 Edge")
        return 1

    work = pathlib.Path(__file__).resolve().parent.parent / "backend" / "var" / f"fp-{uuid.uuid4().hex[:6]}"
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

        cdp.evaluate("location.hash='#/fees'")
        time.sleep(3)
        list_shot = cdp.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
        pathlib.Path(args.out_list).write_bytes(base64.b64decode(list_shot["data"]))

        print("点击案件名称：", cdp.evaluate(
            "(()=>{const a=document.querySelector('tbody tr .name-link');"
            "if(!a)return 'none';a.click();return 'clicked'})()"))
        time.sleep(2)
        print("当前路由：", cdp.evaluate("location.hash"))
        print("是详情页：", cdp.evaluate("document.body.innerText.includes('关联发票') && !document.querySelector('.drawer')"))
        detail_shot = cdp.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
        pathlib.Path(args.out_detail).write_bytes(base64.b64decode(detail_shot["data"]))
        print("详情截图：", args.out_detail)
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
