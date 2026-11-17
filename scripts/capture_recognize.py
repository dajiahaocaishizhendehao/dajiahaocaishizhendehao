"""对正在运行的实例触发一次证书识别，并截取识别确认窗口（含文件预览）。

前提：服务已启动（127.0.0.1:5173），库中至少有一条可识别的材料。

    python scripts/capture_recognize.py --out docs/screenshot-recognize.png
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

CLICK_RECOGNIZE = (
    "(()=>{const rows=[...document.querySelectorAll('tbody tr')];"
    "for(const r of rows){const b=[...r.querySelectorAll('button')]"
    ".find(x=>x.textContent.trim()==='识别');if(b){b.click();return 'clicked'}}return 'none'})()"
)


def main() -> int:
    parser = argparse.ArgumentParser(description="截取识别确认窗口")
    parser.add_argument("--out", default="docs/screenshot-recognize.png")
    parser.add_argument("--base", default="http://127.0.0.1:5173")
    parser.add_argument("--wait", type=int, default=150, help="等待识别完成的最长秒数")
    args = parser.parse_args()

    edge = find_edge()
    if edge is None:
        print("未找到 Microsoft Edge。")
        return 1

    work = pathlib.Path(__file__).resolve().parent.parent / "backend" / "var" / f"shot-{uuid.uuid4().hex[:6]}"
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
            "--window-size=1440,1000",
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
            {"width": 1440, "height": 1000, "deviceScaleFactor": 1, "mobile": False},
        )
        cdp.call("Page.navigate", {"url": f"{args.base}/#/login"})
        time.sleep(2)
        cdp.evaluate(LOGIN)
        time.sleep(2)
        cdp.evaluate("location.hash='#/materials'")
        time.sleep(3)

        print("点击识别：", cdp.evaluate(CLICK_RECOGNIZE))

        deadline = time.time() + args.wait
        ready = False
        while time.time() < deadline:
            state = cdp.evaluate(
                "document.querySelector('.recog-sheet, .preview-box img') ? 'preview' : "
                "(document.querySelector('.recog-modal, .drawer') ? 'drawer' : 'none')"
            )
            if state == "preview":
                ready = True
                break
            time.sleep(2)

        print("预览状态：", "已显示" if ready else "未显示（可能识别较慢）")
        time.sleep(1)
        shot = cdp.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
        out = pathlib.Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(base64.b64decode(shot["data"]))
        print(f"已保存：{out}（{out.stat().st_size} 字节）")
        return 0 if ready else 2
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
