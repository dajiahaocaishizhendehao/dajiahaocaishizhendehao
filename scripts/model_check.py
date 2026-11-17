"""ORM 模型静态检查（零依赖）。

在没有数据库、也没有 SQLAlchemy 的环境里，仍能提前发现两类高频错误：
1. 代码里访问了模型上不存在的属性（拼写错误、字段改名漏改）；
2. ForeignKey("表.列") 指向不存在的表或列。

用法：
    python scripts/model_check.py
"""

from __future__ import annotations

import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
MODELS = BACKEND / "app" / "models.py"

# SQLAlchemy 在类上提供的通用属性，不属于业务字段。
BUILTIN_CLASS_ATTRS = {
    "metadata",
    "registry",
    "query",
    "id",
}


def collect_classes() -> tuple[dict[str, set[str]], dict[str, str]]:
    """返回 (类名 -> 可用属性集合, 表名 -> 类名)。"""

    tree = ast.parse(MODELS.read_text(encoding="utf-8-sig"))
    class_bodies: dict[str, tuple[list[str], set[str]]] = {}
    table_of_class: dict[str, str] = {}

    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        bases = [
            base.id for base in node.bases if isinstance(base, ast.Name)
        ]
        attrs: set[str] = set()
        for statement in node.body:
            if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
                attrs.add(statement.target.id)
            elif isinstance(statement, ast.Assign):
                for target in statement.targets:
                    if isinstance(target, ast.Name):
                        attrs.add(target.id)
                        if target.id == "__tablename__" and isinstance(statement.value, ast.Constant):
                            table_of_class[node.name] = str(statement.value.value)
            elif isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                attrs.add(statement.name)
        class_bodies[node.name] = (bases, attrs)

    resolved: dict[str, set[str]] = {}

    def resolve(name: str, seen: set[str] | None = None) -> set[str]:
        if name in resolved:
            return resolved[name]
        seen = seen or set()
        if name in seen or name not in class_bodies:
            return set()
        seen.add(name)
        bases, attrs = class_bodies[name]
        merged = set(attrs)
        for base in bases:
            merged |= resolve(base, seen)
        resolved[name] = merged
        return merged

    for name in class_bodies:
        resolve(name)

    return resolved, table_of_class


def collect_tables(classes: dict[str, set[str]], table_of_class: dict[str, str]) -> dict[str, set[str]]:
    tables: dict[str, set[str]] = {}
    for class_name, table_name in table_of_class.items():
        tables[table_name] = set(classes.get(class_name, set()))
    return tables


def iter_source_files():
    """只遍历业务源码；跳过虚拟环境与缓存，避免把第三方包自带测试当成业务代码。"""

    for path in BACKEND.rglob("*.py"):
        if any(part in {".venv", "venv", "__pycache__", "site-packages"} for part in path.parts):
            continue
        yield path


def collect_foreign_keys() -> list[tuple[pathlib.Path, int, str]]:
    found: list[tuple[pathlib.Path, int, str]] = []
    for path in iter_source_files():
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "ForeignKey":
                if node.args and isinstance(node.args[0], ast.Constant):
                    found.append((path, node.lineno, str(node.args[0].value)))
    return found


def main() -> int:
    classes, table_of_class = collect_classes()
    tables = collect_tables(classes, table_of_class)
    errors: list[str] = []

    # 1. FK 目标存在性
    for path, lineno, target in collect_foreign_keys():
        if "." not in target:
            errors.append(f"{path.name}:{lineno} ForeignKey 格式不是 表.列：{target}")
            continue
        table, column = target.split(".", 1)
        if table not in tables:
            errors.append(f"{path.name}:{lineno} ForeignKey 指向不存在的表：{table}")
            continue
        if column not in tables[table]:
            errors.append(f"{path.name}:{lineno} ForeignKey 指向不存在的列：{table}.{column}")

    # 2. 属性访问存在性
    model_names = set(classes)
    checked = 0
    for path in iter_source_files():
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id in model_names
            ):
                continue
            # 只检查 ORM 模型类，跳过同名局部变量（例如 Base、Mixin 不是模型）
            if node.value.id in {"Base", "IdMixin", "AuditMixin"}:
                continue
            checked += 1
            available = classes[node.value.id] | BUILTIN_CLASS_ATTRS
            if node.attr not in available:
                errors.append(
                    f"{path.name}:{node.lineno} {node.value.id}.{node.attr} 不是该模型声明的字段或关系"
                )

    print(f"模型类 {len(classes)} 个，数据表 {len(tables)} 张，检查属性访问 {checked} 处")
    print()
    if errors:
        print("发现问题：")
        for error in errors:
            print(f" - {error}")
        return 1

    print("模型检查通过：所有外键目标存在，代码中引用的模型字段均已声明。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
