"""从路由声明生成接口文档（零依赖，不启动服务）。

用法：
    python scripts/gen_api_doc.py            # 写入 docs/API.md
    python scripts/gen_api_doc.py --stdout   # 只打印

文档由静态解析生成，因此可以在没有安装 FastAPI 的环境下得到接口清单；
字段级细节仍以运行时 /docs 的 OpenAPI 为准。
"""

from __future__ import annotations

import argparse
import datetime
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from api_audit import collect  # noqa: E402

MODULE_TITLES = {
    "auth.py": "认证",
    "assets.py": "知识产权档案",
    "certificates.py": "证书",
    "materials.py": "电子材料",
    "dates.py": "日期与提醒",
    "fees.py": "费用与发票",
    "meta.py": "基础资料",
    "stats.py": "统计",
    "admin.py": "系统管理",
}

AUTH_LABELS = {
    "get_current_user": "登录即可",
    "require_write": "需写权限（admin / ip_admin）",
    "require_admin": "需管理员",
}


def render() -> str:
    endpoints = collect()
    lines: list[str] = []
    lines.append("# 接口清单")
    lines.append("")
    lines.append("> 本文件由 `python scripts/gen_api_doc.py` 从路由声明静态生成，请勿手工编辑。")
    lines.append(f"> 生成日期：{datetime.date.today().isoformat()}；接口总数：{len(endpoints)}。")
    lines.append("")
    lines.append("运行时完整 OpenAPI（含请求体字段）请访问 `http://127.0.0.1:8000/docs`。")
    lines.append("")

    by_module: dict[str, list[dict]] = {}
    for item in endpoints:
        by_module.setdefault(item["module"], []).append(item)

    for module, items in by_module.items():
        lines.append(f"## {MODULE_TITLES.get(module, module)}")
        lines.append("")
        lines.append("| 方法 | 路径 | 响应模型 | 权限 |")
        lines.append("|---|---|---|---|")
        for item in items:
            auth = "、".join(AUTH_LABELS.get(name, name) for name in item["auth"]) or "无（公开）"
            model = item.get("response_model") or "—"
            lines.append(f"| `{item['method']}` | `{item['path']}` | `{model}` | {auth} |")
        lines.append("")

    lines.append("## 约定")
    lines.append("")
    lines.append("- 所有接口前缀为 `/api`；`/health` 为健康检查。")
    lines.append("- 列表接口统一返回 `{items, total, page, page_size}`。")
    lines.append("- 删除为逻辑删除，返回 `204`。")
    lines.append("- 金额使用定点小数，接口中为字符串形式的十进制数。")
    lines.append("- 日期为 `YYYY-MM-DD`，时间为带时区 ISO 8601。")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成接口文档")
    parser.add_argument("--stdout", action="store_true", help="只打印不写文件")
    args = parser.parse_args()

    content = render()
    if args.stdout:
        print(content)
        return 0

    target = ROOT / "docs" / "API.md"
    try:
        target.write_text(content, encoding="utf-8")
    except PermissionError:
        print(f"无法写入 {target}（当前进程没有该目录的写权限）。", file=sys.stderr)
        print("请用 --stdout 输出后由具备权限的编辑器保存，或以更高权限运行。", file=sys.stderr)
        return 2
    print(f"已生成 {target.relative_to(ROOT)}（{len(content.splitlines())} 行）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
