"""把用户真实年费台账导入系统。

台账列：我方文号 | 申请号 | 案件名称 | 专利所有权人 | 官费应缴纳日 | 本次官费缴纳至 | 本次官费缴纳金额 | 缴纳日期

导入策略：
- 每行 = 一件专利档案（docket_no 取我方文号，便于按文号检索）；
- 权利人按名称复用或新建；
- 生成一条“年费”费用记录，包含应缴日、实缴日、缴至日与金额。

用法：
    python scripts/import_annuity_ledger.py --file "<台账.xlsx>" --base http://127.0.0.1:5173
"""

from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

from openpyxl import load_workbook

DEFAULT_USER = "admin"
DEFAULT_PASSWORD = "Admin@12345"


def http(base: str, method: str, path: str, *, token: str | None = None, body: dict | None = None):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(f"{base}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read()
            return response.status, json.loads(payload) if payload else {}
    except urllib.error.HTTPError as error:
        payload = error.read()
        try:
            return error.code, json.loads(payload)
        except json.JSONDecodeError:
            return error.code, {"detail": payload.decode("utf-8", "replace")}


def as_date(value) -> datetime.date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="导入年费台账")
    parser.add_argument("--file", required=True)
    parser.add_argument("--base", default="http://127.0.0.1:5173")
    parser.add_argument("--username", default=DEFAULT_USER)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    path = pathlib.Path(args.file)
    if not path.exists():
        print(f"文件不存在：{path}")
        return 1

    workbook = load_workbook(path, data_only=True)
    sheet = workbook.active
    rows = []
    for row in sheet.iter_rows(min_row=2, values_only=True):
        if not row or not row[2]:
            continue  # 跳过空行与合计行
        rows.append(row)

    print(f"读取到 {len(rows)} 条专利年费记录")

    status, payload = http(
        args.base, "POST", "/api/auth/login", body={"username": args.username, "password": args.password}
    )
    if status != 200:
        print(f"登录失败：{status} {payload}")
        return 1
    token = payload["access_token"]

    status, page = http(args.base, "GET", "/api/parties?page=1&page_size=200", token=token)
    parties = {item["name"]: item["id"] for item in page.get("items", [])} if status == 200 else {}

    created_assets = 0
    skipped_assets = 0
    created_fees = 0
    skipped_fees = 0
    problems: list[str] = []

    for row in rows:
        docket, app_no, name, owner, due, coverage, amount, paid = row[:8]
        docket = str(docket).strip()
        name = str(name).strip()
        owner = str(owner).strip()

        if args.dry_run:
            print(f"[dry-run] {docket} | {name} | {owner} | 应缴 {as_date(due)} | 缴至 {as_date(coverage)} | {amount}")
            continue

        party_id = parties.get(owner)
        if owner and not party_id:
            status, created = http(args.base, "POST", "/api/parties", token=token, body={"name": owner})
            if status == 201:
                party_id = created["id"]
                parties[owner] = party_id
            else:
                problems.append(f"权利人创建失败 {owner}: {status}")

        payload_body = {
            "name": name,
            "docket_no": docket,
            "ip_type": "patent",
            "status_group": "granted",
            "patent": {
                "patent_type": "invention",
                "application_no": str(app_no).strip() if app_no else None,
            },
        }
        if party_id:
            payload_body["parties"] = [{"party_id": party_id, "role": "patentee", "seq": 0}]

        status, created = http(args.base, "POST", "/api/assets", token=token, body=payload_body)
        if status == 409:
            status, page = http(
                args.base, "GET", f"/api/assets?q={urllib.parse.quote(docket)}", token=token
            )
            items = page.get("items", []) if status == 200 else []
            asset_id = items[0]["id"] if items else None
            skipped_assets += 1
        elif status == 201:
            asset_id = created["id"]
            created_assets += 1
        else:
            problems.append(f"档案创建失败 {docket}: {status} {created.get('detail')}")
            continue

        if not asset_id:
            problems.append(f"未找到档案 ID：{docket}")
            continue

        fee_body = {
            "ip_asset_id": asset_id,
            "fee_type": "annuity",
            "description": "专利年费（台账导入）",
            "amount_due": str(amount),
            "amount_paid": str(amount),
            "currency": "CNY",
            "due_date": as_date(due).isoformat() if as_date(due) else None,
            "paid_date": as_date(paid).isoformat() if as_date(paid) else None,
            "coverage_end_date": as_date(coverage).isoformat() if as_date(coverage) else None,
            "payee": "国家知识产权局",
        }

        # 幂等：同一案件同一缴至日已存在则跳过，避免重复导入产生重复年费记录。
        coverage_text = fee_body["coverage_end_date"]
        status, existing = http(
            args.base, "GET", f"/api/fees?ip_asset_id={asset_id}&page=1&page_size=200", token=token
        )
        if status == 200 and any(
            item.get("coverage_end_date") == coverage_text for item in existing.get("items", [])
        ):
            skipped_fees += 1
            continue

        status, created_fee = http(args.base, "POST", "/api/fees", token=token, body=fee_body)
        if status == 201:
            created_fees += 1
        else:
            problems.append(f"费用创建失败 {docket}: {status} {created_fee.get('detail')}")

    if args.dry_run:
        return 0

    print()
    print(f"新建档案 {created_assets} 件，已存在 {skipped_assets} 件，新建年费记录 {created_fees} 条，跳过已存在 {skipped_fees} 条")
    if problems:
        print(f"问题 {len(problems)} 项：")
        for item in problems[:20]:
            print(f" - {item}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
