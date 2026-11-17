"""接口静态审计（零依赖）。

以 AST 解析 backend/app/routers，回答三个问题：
1. 是否存在重复的「方法 + 路径」；
2. 是否存在没有任何鉴权依赖的接口（登录接口除外）；
3. 路由模块是否都已在 api_router 中注册。

用法：
    python scripts/api_audit.py           # 打印接口清单并校验
    python scripts/api_audit.py --list    # 仅打印清单
"""

from __future__ import annotations

import argparse
import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
ROUTERS = ROOT / "backend" / "app" / "routers"

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}
AUTH_DEPENDENCIES = {"get_current_user", "require_write", "require_admin"}
# 允许公开访问的接口，必须逐条列出并说明原因。
PUBLIC_ENDPOINTS = {
    ("POST", "/api/auth/login"): "登录接口本身不能要求已登录",
}


def _call_name(node: ast.AST) -> str | None:
    """取调用名或引用名。既支持 Depends(x) 也支持裸的 x。"""

    if isinstance(node, ast.Call):
        return _call_name(node.func)
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _router_prefix(tree: ast.Module) -> str:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "router":
                if isinstance(node.value, ast.Call):
                    for keyword in node.value.keywords:
                        if keyword.arg == "prefix" and isinstance(keyword.value, ast.Constant):
                            return str(keyword.value.value)
    return ""


def _auth_dependencies(function: ast.FunctionDef) -> set[str]:
    found: set[str] = set()
    for default in list(function.args.defaults) + [d for d in function.args.kw_defaults if d]:
        if isinstance(default, ast.Call) and _call_name(default) == "Depends":
            for argument in default.args:
                name = _call_name(argument)
                if name:
                    found.add(name)
    return found


def collect() -> list[dict]:
    endpoints: list[dict] = []
    for path in sorted(ROUTERS.glob("*.py")):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        prefix = _router_prefix(tree)
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                method = _call_name(decorator)
                if method not in HTTP_METHODS:
                    continue
                route = ""
                if decorator.args and isinstance(decorator.args[0], ast.Constant):
                    route = str(decorator.args[0].value)
                response_model = ""
                status_code = ""
                for keyword in decorator.keywords:
                    if keyword.arg == "response_model":
                        response_model = ast.unparse(keyword.value)
                    elif keyword.arg == "status_code":
                        status_code = ast.unparse(keyword.value).split(".")[-1]
                full = f"/api{prefix}{route}"
                endpoints.append(
                    {
                        "module": path.name,
                        "method": method.upper(),
                        "path": full,
                        "function": node.name,
                        "auth": sorted(_auth_dependencies(node) & AUTH_DEPENDENCIES),
                        "response_model": response_model,
                        "status_code": status_code,
                    }
                )
    return endpoints


def registered_modules() -> set[str]:
    init = ROUTERS / "__init__.py"
    tree = ast.parse(init.read_text(encoding="utf-8-sig"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "app.routers":
            for alias in node.names:
                modules.add(f"{alias.name}.py")
    return modules


def main() -> int:
    parser = argparse.ArgumentParser(description="接口静态审计")
    parser.add_argument("--list", action="store_true", help="仅打印接口清单")
    args = parser.parse_args()

    endpoints = collect()
    problems: list[str] = []

    print(f"共解析接口 {len(endpoints)} 个\n")
    print(f"{'方法':<7}{'路径':<42}{'处理函数':<26}{'鉴权'}")
    print("-" * 96)
    for item in endpoints:
        auth = ", ".join(item["auth"]) if item["auth"] else "无"
        print(f"{item['method']:<7}{item['path']:<42}{item['function']:<26}{auth}")

    seen: dict[tuple[str, str], str] = {}
    for item in endpoints:
        key = (item["method"], item["path"])
        if key in seen:
            problems.append(f"重复路由：{item['method']} {item['path']}（{seen[key]} 与 {item['function']}）")
        else:
            seen[key] = item["function"]

        if not item["auth"]:
            allowed = PUBLIC_ENDPOINTS.get(key)
            if allowed is None:
                problems.append(f"缺少鉴权依赖：{item['method']} {item['path']}（{item['function']}）")

    declared = {item["module"] for item in endpoints}
    registered = registered_modules()
    for missing in sorted(declared - registered):
        problems.append(f"路由模块未注册：{missing}")

    if args.list:
        return 0

    print()
    if problems:
        print("发现问题：")
        for problem in problems:
            print(f" - {problem}")
        return 1

    print("接口审计通过：无重复路由，所有接口均声明了鉴权依赖，路由模块均已注册。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
