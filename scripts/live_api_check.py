"""真实启动 FastAPI 服务并跑一遍主流程（端到端验证）。

前提：解释器里装有 fastapi / sqlalchemy / uvicorn（本机可用 .deps 目录提供）。
不需要 PostgreSQL：使用 SQLite 文件库；不需要 pytest 与 httpx：用标准库 urllib 发请求。

用法（在仓库根目录）：

    set PYTHONPATH=<backend>;<deps>
    python scripts/live_api_check.py

脚本会：
1. 建临时 SQLite 库并写入演示账号；
2. 以子进程启动 uvicorn；
3. 通过 HTTP 跑一遍主要业务流程；
4. 结束后关闭服务、删除临时库。
"""

from __future__ import annotations

import json
import os
import pathlib
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT = pathlib.Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"

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


def http(
    base: str,
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: dict | None = None,
    raw_body: bytes | None = None,
    content_type: str = "application/json",
) -> tuple[int, bytes]:
    url = f"{base}{path}"
    data = None
    headers = {}
    if raw_body is not None:
        data = raw_body
        headers["Content-Type"] = content_type
    elif body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def as_json(payload: bytes) -> dict:
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}


def seed_database(db_url: str) -> None:
    """在启动服务前写入账号数据。"""

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
        db.add(
            User(
                username="normal",
                display_name="普通用户",
                password_hash=security.hash_password("Passw0rd!"),
                role=UserRole.USER,
            )
        )
        db.commit()
    # 关闭连接池，否则 Windows 下临时库文件会被占用而无法删除。
    engine.dispose()


def wait_for_health(base: str, timeout: float = 40.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            status, _ = http(base, "GET", "/health")
            if status == 200:
                return True
        except OSError:
            pass
        time.sleep(0.4)
    return False


def main() -> int:
    # 默认用工作区内的临时 SQLite 库；设置 IPMS_LIVE_DSN 可指向真实数据库
    # （例如 PostgreSQL），此时不会删除数据库文件。
    external_dsn = os.environ.get("IPMS_LIVE_DSN")
    if external_dsn:
        tmpdir = None
        db_url = external_dsn
        print(f"使用外部数据库：{_redact(db_url)}")
    else:
        tmpdir = BACKEND / "var" / f"live-check-{uuid.uuid4().hex[:8]}"
        tmpdir.mkdir(parents=True, exist_ok=True)
        db_path = tmpdir / "ipms.db"
        db_url = f"sqlite+pysqlite:///{db_path.as_posix()}"

    seed_database(db_url)

    port = free_port()
    base = f"http://127.0.0.1:{port}"
    env = dict(os.environ)
    env["DATABASE_URL"] = db_url
    env["PYTHONPATH"] = os.pathsep.join([str(BACKEND), env.get("PYTHONPATH", "")]).strip(os.pathsep)

    print(f"启动服务：{base}（SQLite 临时库）")
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=str(BACKEND),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        if not wait_for_health(base):
            output = ""
            if server.stdout:
                server.stdout.close()
            print("FAIL 服务未能在限定时间内就绪")
            return 1
        check(True, "服务启动并通过 /health")

        # 1. 未登录访问
        status, _ = http(base, "GET", "/api/assets")
        check(status == 401, f"未登录访问档案列表返回 401（实际 {status}）")

        # 2. 登录
        status, payload = http(base, "POST", "/api/auth/login", body={"username": "admin", "password": "Passw0rd!"})
        admin_token = as_json(payload).get("access_token")
        check(status == 200 and bool(admin_token), f"管理员登录成功（HTTP {status}）")

        status, payload = http(base, "POST", "/api/auth/login", body={"username": "admin", "password": "wrong"})
        check(status == 401, f"错误密码被拒绝（HTTP {status}）")

        # 3. 创建专利档案
        asset_body = {
            "name": "端到端验证专利",
            "ip_type": "patent",
            "status_group": "in_progress",
            "patent": {"patent_type": "invention", "application_no": "CN-LIVE-1"},
        }
        status, payload = http(base, "POST", "/api/assets", token=admin_token, body=asset_body)
        asset = as_json(payload)
        asset_id = asset.get("id")
        check(status == 201 and bool(asset_id), f"创建专利档案（HTTP {status}）")
        check("asset_no" not in asset, "创建响应不再返回内部编号")

        # 第二条档案，用于验证列表与统计
        status, payload = http(
            base,
            "POST",
            "/api/assets",
            token=admin_token,
            body={
                "name": "第二条专利",
                "ip_type": "patent",
                "patent": {"patent_type": "utility"},
            },
        )
        check(status == 201, f"创建第二条档案（HTTP {status}）")

        # 4. 类型隔离
        bad_body = dict(asset_body, trademark={"word_mark": "X"})
        status, _ = http(base, "POST", "/api/assets", token=admin_token, body=bad_body)
        check(status == 422, f"跨类型字段被拒绝（HTTP {status}）")

        # 5. 列表与筛选
        status, payload = http(base, "GET", "/api/assets?ip_type=patent", token=admin_token)
        listing = as_json(payload)
        check(status == 200 and listing.get("total") == 2, f"列表返回两条档案（total={listing.get('total')}）")

        status, payload = http(
            base, "GET", "/api/assets?q=" + urllib.parse.quote("端到端验证专利"), token=admin_token
        )
        check(as_json(payload).get("total") == 1, "关键字搜索命中 1 条")

        # 6. 详情
        status, payload = http(base, "GET", f"/api/assets/{asset_id}", token=admin_token)
        detail = as_json(payload)
        check(
            status == 200 and detail.get("patent", {}).get("application_no") == "CN-LIVE-1",
            "档案详情返回专业字段",
        )

        # 7. 更新状态
        status, payload = http(
            base, "PATCH", f"/api/assets/{asset_id}", token=admin_token, body={"status_group": "granted"}
        )
        check(status == 200 and as_json(payload).get("status_group") == "granted", "更新综合状态为已取得权利")

        # 8. 证书
        status, payload = http(
            base,
            "POST",
            "/api/certificates",
            token=admin_token,
            body={
                "ip_asset_id": asset_id,
                "cert_type": "patent_certificate",
                "cert_no": "CERT-LIVE-1",
                "electronic_status": "archived",
                "paper_status": "in_storage",
                "location": "A柜-01层",
            },
        )
        check(status == 201, f"登记证书（HTTP {status}）")

        # 9. 日期事项与完成
        status, payload = http(
            base,
            "POST",
            "/api/dates",
            token=admin_token,
            body={"title": "答复期限", "date_type": "due", "due_date": "2026-12-01", "ip_asset_id": asset_id},
        )
        date_id = as_json(payload).get("id")
        check(status == 201 and bool(date_id), f"新建日期事项（HTTP {status}）")

        status, payload = http(base, "POST", f"/api/dates/{date_id}/complete", token=admin_token)
        check(status == 200 and as_json(payload).get("status") == "done", "标记日期事项完成")

        # 10. 费用与发票
        status, payload = http(
            base,
            "POST",
            "/api/fees",
            token=admin_token,
            body={"fee_type": "agency", "amount_due": "8000.00", "amount_paid": "3000.00", "ip_asset_id": asset_id},
        )
        fee = as_json(payload)
        fee_id = fee.get("id")
        check(status == 201 and fee.get("status") == "partial", f"费用状态按实付推导为部分支付（{fee.get('status')}）")

        status, payload = http(
            base,
            "POST",
            "/api/invoices",
            token=admin_token,
            body={"ip_asset_id": asset_id, "invoice_no": "INV-LIVE-1", "amount_gross": "8000.00", "fee_ids": [fee_id]},
        )
        check(status == 201 and as_json(payload).get("fee_ids") == [fee_id], "发票关联费用")

        # 11. 材料上传与下载
        boundary = "----ipms" + uuid.uuid4().hex
        content = b"%PDF-1.4\n% live verification material\n"
        multipart = b"".join(
            [
                f"--{boundary}\r\n".encode(),
                b'Content-Disposition: form-data; name="file"; filename="demo.pdf"\r\n',
                b"Content-Type: application/pdf\r\n\r\n",
                content,
                f"\r\n--{boundary}\r\n".encode(),
                b'Content-Disposition: form-data; name="category"\r\n\r\napplication_document\r\n',
                f"--{boundary}--\r\n".encode(),
            ]
        )
        status, payload = http(
            base,
            "POST",
            "/api/materials",
            token=admin_token,
            raw_body=multipart,
            content_type=f"multipart/form-data; boundary={boundary}",
        )
        material = as_json(payload)
        check(status == 201 and material.get("size_bytes") == len(content), f"上传材料（HTTP {status}）")

        if material.get("id"):
            status, downloaded = http(base, "GET", f"/api/materials/{material['id']}/download", token=admin_token)
            check(status == 200 and downloaded == content, "下载材料内容一致")

        # 12. 统计
        status, payload = http(base, "GET", "/api/stats/dashboard", token=admin_token)
        dashboard = as_json(payload)
        check(
            status == 200 and dashboard.get("total_assets") == 2 and dashboard.get("granted_rate") == 50.0,
            f"统计看板（total={dashboard.get('total_assets')}, granted_rate={dashboard.get('granted_rate')}）",
        )
        check(bool(dashboard.get("metrics")), "统计接口返回口径说明")

        status, payload = http(base, "GET", "/api/stats/yearly", token=admin_token)
        check(as_json(payload).get("date_field") == "created_at", "年度统计声明使用 created_at")

        # 13. 导出（CSV 与 Excel）
        status, exported = http(base, "GET", "/api/export/assets.csv", token=admin_token)
        check(status == 200 and "端到端验证专利" in exported.decode("utf-8-sig"), "导出 CSV 含案件名称")

        status, xlsx = http(base, "GET", "/api/export/assets.xlsx", token=admin_token)
        check(status == 200 and xlsx[:2] == b"PK", f"导出 Excel 为合法 xlsx（HTTP {status}）")
        if status == 200 and xlsx[:2] == b"PK":
            try:
                import io as _io

                from openpyxl import load_workbook

                workbook = load_workbook(_io.BytesIO(xlsx))
                sheet = workbook.active
                header = [cell.value for cell in next(sheet.iter_rows(max_row=1))]
                rows = sheet.max_row - 1
                check(header[:2] == ["名称", "类型"], f"Excel 表头正确：{header[:2]}")
                check(rows == 2, f"Excel 数据行数与筛选范围一致（{rows} 行）")
            except ImportError:
                print("     （未安装 openpyxl，跳过 Excel 内容校验）")

        # 14. 导入
        csv_body = "案件名称,知识产权类型\n导入专利,patent\n,patent\n".encode("utf-8")
        status, payload = http(
            base,
            "POST",
            "/api/import/assets",
            token=admin_token,
            raw_body=b"".join(
                [
                    f"--{boundary}\r\n".encode(),
                    b'Content-Disposition: form-data; name="file"; filename="assets.csv"\r\n',
                    b"Content-Type: text/csv\r\n\r\n",
                    csv_body,
                    f"\r\n--{boundary}--\r\n".encode(),
                ]
            ),
            content_type=f"multipart/form-data; boundary={boundary}",
        )
        result = as_json(payload)
        check(
            status == 200 and result.get("created") == 1 and result.get("skipped") == 1,
            f"CSV 导入创建 1 条、跳过 1 条（{result.get('created')}/{result.get('skipped')}）",
        )

        # 15. 权限
        status, payload = http(base, "POST", "/api/auth/login", body={"username": "normal", "password": "Passw0rd!"})
        normal_token = as_json(payload).get("access_token")
        status, _ = http(base, "POST", "/api/assets", token=normal_token, body=asset_body)
        check(status == 403, f"普通用户写入返回 403（实际 {status}）")

        status, payload = http(base, "GET", "/api/assets", token=normal_token)
        normal_listing = as_json(payload)
        check(
            status == 200 and normal_listing.get("total") == 3,
            f"普通用户可查看全部档案（total={normal_listing.get('total')}）",
        )

        # 16. 审计
        status, payload = http(base, "GET", "/api/audit-logs?object_type=ip_asset", token=admin_token)
        check(status == 200 and as_json(payload).get("total", 0) >= 1, "操作审计已记录")

        # 18. 逻辑删除后不可见
        status, _ = http(base, "DELETE", f"/api/assets/{asset_id}", token=admin_token)
        check(status == 204, f"逻辑删除返回 204（实际 {status}）")
        status, _ = http(base, "GET", f"/api/assets/{asset_id}", token=admin_token)
        check(status == 404, f"删除后详情返回 404（实际 {status}）")

    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        if tmpdir is not None:
            for path in sorted(tmpdir.rglob("*"), reverse=True):
                try:
                    if path.is_file():
                        path.unlink()
                    elif path.is_dir():
                        path.rmdir()
                except OSError:
                    pass
            try:
                tmpdir.rmdir()
            except OSError:
                pass
    print()
    if failures:
        print(f"端到端验证失败 {len(failures)} 项 / 共 {checks} 项：")
        for item in failures:
            print(f" - {item}")
        return 1

    print(f"端到端验证全部通过（{checks} 项检查）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
