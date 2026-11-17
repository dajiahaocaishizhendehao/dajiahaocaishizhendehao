"""前后端契约一致性检查（零依赖）。

把 FastAPI 的 Pydantic 响应模型与前端 TypeScript 接口做字段比对：
- 前端声明了后端没有的字段 → 错误（运行时一定是 undefined）；
- 后端有前端没声明的字段 → 提示（前端未使用，不算错误）。

用法：
    python scripts/contract_check.py
"""

from __future__ import annotations

import ast
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMAS = ROOT / "backend" / "app" / "schemas.py"
API_TS = ROOT / "frontend" / "src" / "api.ts"

# Pydantic 模型 -> TypeScript 接口
MAPPING = {
    "AssetListItem": "AssetListItem",
    "AssetDetail": "AssetDetail",
    # 独立证书前端页面已下线；后端模型暂保留用于历史数据兼容。
    "DateItemOut": "DateItem",
    "DashboardOut": "Dashboard",
    "UserOut": "User",
}

IGNORED_BACKEND_FIELDS = {"model_config"}


def base_names(node: ast.ClassDef) -> list[str]:
    names: list[str] = []
    for base in node.bases:
        if isinstance(base, ast.Name):
            names.append(base.id)
        elif isinstance(base, ast.Attribute):
            names.append(base.attr)
        elif isinstance(base, ast.Subscript) and isinstance(base.value, ast.Name):
            names.append(base.value.id)
    return names


def collect_models() -> dict[str, dict[str, str]]:
    tree = ast.parse(SCHEMAS.read_text(encoding="utf-8-sig"))
    raw: dict[str, tuple[list[str], dict[str, str]]] = {}

    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        fields: dict[str, str] = {}
        for statement in node.body:
            if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
                fields[statement.target.id] = ast.unparse(statement.annotation)
        raw[node.name] = (base_names(node), fields)

    resolved: dict[str, dict[str, str]] = {}

    def resolve(name: str, seen: set[str] | None = None) -> dict[str, str]:
        if name in resolved:
            return resolved[name]
        seen = seen or set()
        if name in seen or name not in raw:
            return {}
        seen.add(name)
        bases, fields = raw[name]
        merged: dict[str, str] = {}
        for base in bases:
            merged.update(resolve(base, seen))
        merged.update(fields)
        resolved[name] = merged
        return merged

    for name in raw:
        resolve(name)
    return resolved


def collect_ts_interfaces() -> dict[str, set[str]]:
    text = API_TS.read_text(encoding="utf-8")
    raw: dict[str, tuple[list[str], set[str]]] = {}

    pattern = re.compile(
        r"export interface (\w+)(?:\s+extends\s+([\w, ]+))?\s*\{(.*?)\n\}", flags=re.S
    )
    for match in pattern.finditer(text):
        name, extends_raw, body = match.group(1), match.group(2) or "", match.group(3)
        bases = [item.strip() for item in extends_raw.split(",") if item.strip()]
        fields: set[str] = set()
        for line in body.splitlines():
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            field = re.match(r"([A-Za-z_]\w*)\??\s*:", line)
            if field:
                fields.add(field.group(1))
        raw[name] = (bases, fields)

    resolved: dict[str, set[str]] = {}

    def resolve(name: str, seen: set[str] | None = None) -> set[str]:
        if name in resolved:
            return resolved[name]
        seen = seen or set()
        if name in seen or name not in raw:
            return set()
        seen.add(name)
        bases, fields = raw[name]
        merged = set(fields)
        for base in bases:
            merged |= resolve(base, seen)
        resolved[name] = merged
        return merged

    for name in raw:
        resolve(name)
    return resolved


def main() -> int:
    models = collect_models()
    interfaces = collect_ts_interfaces()

    errors: list[str] = []
    notes: list[str] = []

    for backend_name, ts_name in MAPPING.items():
        backend_fields = set(models.get(backend_name, {})) - IGNORED_BACKEND_FIELDS
        ts_fields = interfaces.get(ts_name)
        if not backend_fields:
            errors.append(f"未找到后端模型 {backend_name}")
            continue
        if ts_fields is None:
            errors.append(f"未找到前端接口 {ts_name}")
            continue

        extra_in_ts = ts_fields - backend_fields
        missing_in_ts = backend_fields - ts_fields
        if extra_in_ts:
            status = "字段不一致"
        elif missing_in_ts:
            status = "前端少用字段"
        else:
            status = "一致"
        print(f"{backend_name:<18} ↔ {ts_name:<16} 后端 {len(backend_fields):>2} 字段 / 前端 {len(ts_fields):>2} 字段  {status}")

        for field in sorted(extra_in_ts):
            errors.append(f"{ts_name}.{field} 在后端 {backend_name} 中不存在")
        for field in sorted(missing_in_ts):
            notes.append(f"{ts_name} 未使用字段 {field}")

    if notes:
        print("\n提示（后端有、前端未使用）：")
        for note in notes:
            print(f" - {note}")

    print()
    if errors:
        print("契约不一致：")
        for error in errors:
            print(f" - {error}")
        return 1

    print("契约检查通过：前端引用的字段均存在于后端响应模型。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
