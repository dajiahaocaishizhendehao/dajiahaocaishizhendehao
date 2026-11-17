"""仓库自检脚本（仅依赖 Python 标准库）。

用法：
    python scripts/verify.py           # 离线静态检查，并在依赖就绪时执行测试/类型检查
    python scripts/verify.py --offline # 只做离线检查

检查内容：
1. 后端 Python 语法编译；
2. 后端项目内导入是否可解析；
3. 前端 SFC 结构与相对导入是否可解析；
4. 前端 api.ts 的导出名与实际调用是否一致；
5. 若已安装 pytest，则执行后端测试；若已安装前端依赖，则执行类型检查。
"""

from __future__ import annotations

import argparse
import ast
import os
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
FRONTEND_SRC = ROOT / "frontend" / "src"

failures: list[str] = []


def run_command(
    args: list[str], cwd: pathlib.Path = ROOT, extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """统一用 UTF-8 执行子进程，避免 Windows 默认代码页导致中文乱码或解码失败。"""

    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


def step(title: str) -> None:
    print(f"\n== {title} ==")


def compile_backend() -> None:
    step("后端 Python 语法编译")
    result = run_command([sys.executable, "-m", "compileall", "-q", str(BACKEND)])
    if result.returncode != 0:
        failures.append("后端语法编译失败")
        print(result.stdout, result.stderr)
    else:
        print("通过")


def _module_names(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
    return names


def check_backend_imports() -> None:
    step("后端项目内导入解析")
    modules: dict[str, pathlib.Path] = {}
    for path in BACKEND.rglob("*.py"):
        if any(part in {".venv", "venv", "__pycache__", "site-packages"} for part in path.parts):
            continue
        parts = list(path.relative_to(BACKEND).with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        modules[".".join(parts)] = path

    cache: dict[str, set[str]] = {}
    errors: list[str] = []
    checked = 0
    for path in sorted(modules.values()):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
            if not (isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app")):
                continue
            base = node.module
            if base not in modules and not any(m.startswith(base + ".") for m in modules):
                errors.append(f"{path}: 缺少模块 {base}")
                continue
            if base not in cache:
                cache[base] = _module_names(modules[base]) if base in modules else set()
            exported = cache[base]
            for alias in node.names:
                checked += 1
                if alias.name == "*" or alias.name in exported or f"{base}.{alias.name}" in modules:
                    continue
                errors.append(f"{path}: {base} 未定义 {alias.name}")

    print(f"检查导入 {checked} 处，错误 {len(errors)} 处")
    for error in errors:
        print(f" - {error}")
    if errors:
        failures.append("后端导入解析失败")


def _resolve_relative(base: pathlib.Path, spec: str) -> bool:
    target = (base / spec).resolve()
    candidates = [target]
    if target.suffix == "":
        candidates += [target.with_suffix(".ts"), pathlib.Path(str(target) + ".vue"), target / "index.ts"]
    return any(candidate.exists() for candidate in candidates)


def check_frontend() -> None:
    step("前端结构与导入检查")
    errors: list[str] = []
    vue_files = list(FRONTEND_SRC.rglob("*.vue"))
    all_files = vue_files + list(FRONTEND_SRC.rglob("*.ts"))

    for path in all_files:
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".vue":
            for tag in ("template", "script", "style"):
                opened = len(re.findall(rf"<{tag}[ >]", text))
                closed = len(re.findall(rf"</{tag}>", text))
                if opened != closed:
                    errors.append(f"{path.name}: <{tag}> 标签不配对 ({opened}/{closed})")
            if text.count("{{") != text.count("}}"):
                errors.append(f"{path.name}: 插值括号不配对")
        for match in re.finditer(r"from '(\.[^']+)'", text):
            if not _resolve_relative(path.parent, match.group(1)):
                errors.append(f"{path.name}: 无法解析导入 {match.group(1)}")

    api_file = FRONTEND_SRC / "api.ts"
    if api_file.exists():
        api_text = api_file.read_text(encoding="utf-8")
        exported = set(
            re.findall(r"export\s+(?:async\s+)?(?:interface|type|const|function|class)\s+(\w+)", api_text)
        ) | {"api"}
        members = set(re.findall(r"^\s{2}(\w+):", api_text, flags=re.M))
        members |= set(re.findall(r"^\s{2}(?:async\s+)?(\w+)\s*\(", api_text, flags=re.M))
        for path in all_files:
            text = path.read_text(encoding="utf-8")
            for match in re.finditer(r"import\s+(?:type\s+)?\{([^}]+)\}\s+from\s+'[^']*api'", text):
                for raw in match.group(1).split(","):
                    name = raw.strip().replace("type ", "").split(" as ")[0].strip()
                    if name and name not in exported:
                        errors.append(f"{path.name}: api.ts 未导出 {name}")
            for match in re.finditer(r"\bapi\.(\w+)\(", text):
                if match.group(1) not in members:
                    errors.append(f"{path.name}: api 无成员 {match.group(1)}")

    # 路由跳转目标必须已在 router.ts 注册
    router_file = FRONTEND_SRC / "router.ts"
    if router_file.exists():
        router_text = router_file.read_text(encoding="utf-8")
        declared = set(re.findall(r"path:\s*'([^']*)'", router_text))
        declared_prefixes = {path for path in declared}
        for path in all_files:
            text = path.read_text(encoding="utf-8")
            for match in re.finditer(r'to="(/[^"$]*)"', text):
                target = match.group(1)
                if target in declared_prefixes:
                    continue
                if any(target.startswith(item + "/") for item in declared_prefixes if item != "/"):
                    continue
                errors.append(f"{path.name}: 跳转目标未在 router.ts 注册：{target}")

    print(f"检查文件 {len(all_files)} 个（含 {len(vue_files)} 个 Vue 组件），错误 {len(errors)} 处")
    for error in errors:
        print(f" - {error}")
    if errors:
        failures.append("前端结构与导入检查失败")


def run_model_check() -> None:
    step("ORM 模型静态检查")
    result = run_command([sys.executable, str(ROOT / "scripts" / "model_check.py")])
    lines = (result.stdout or "").strip().splitlines()
    print(lines[-1] if lines else "(无输出)")
    if result.returncode != 0:
        for line in lines[-20:]:
            print(f" {line}")
        failures.append("ORM 模型静态检查失败")


def run_api_audit() -> None:
    step("接口静态审计")
    result = run_command([sys.executable, str(ROOT / "scripts" / "api_audit.py")])
    lines = (result.stdout or "").strip().splitlines()
    print(lines[-1] if lines else "(无输出)")
    if result.returncode != 0:
        for line in lines[-20:]:
            print(f" {line}")
        failures.append("接口审计失败")


def run_contract_check() -> None:
    step("前后端契约检查")
    result = run_command([sys.executable, str(ROOT / "scripts" / "contract_check.py")])
    lines = (result.stdout or "").strip().splitlines()
    print(lines[-1] if lines else "(无输出)")
    if result.returncode != 0:
        for line in lines[-20:]:
            print(f" {line}")
        failures.append("前后端契约检查失败")


DOMAIN_TEST_MODULES = ["test_domain.py", "test_query.py"]


def run_domain_tests() -> None:
    """纯业务规则测试只依赖标准库，任何环境都应该执行。"""
    step("纯业务规则单元测试（零依赖）")
    for pattern in DOMAIN_TEST_MODULES:
        result = run_command(
            [
                sys.executable,
                "-m",
                "unittest",
                "discover",
                "-s",
                "backend/tests",
                "-t",
                "backend",
                "-p",
                pattern,
            ]
        )
        output = ((result.stderr or "") + (result.stdout or "")).strip().splitlines()
        ran = next((line for line in reversed(output) if line.startswith("Ran ")), "")
        summary = next((line for line in reversed(output) if line.startswith(("OK", "FAILED"))), "")
        print(f" - {pattern:<20}{ran:<26}{summary}")
        if result.returncode != 0:
            failures.append(f"业务规则测试失败：{pattern}")
            for line in output[-12:]:
                print(f"    {line}")


_pydantic_python: str | None = None

# 这些测试需要第三方库（pydantic / fastapi / starlette），但都不需要数据库。
THIRD_PARTY_TEST_MODULES = [
    "test_schemas.py",
    "test_http_contract.py",
    "test_config.py",
    "test_storage.py",
    "test_request_context.py",
]


def _find_pydantic_python() -> str | None:
    candidates: list[str] = []
    if os.environ.get("IPMS_SCHEMA_PYTHON"):
        candidates.append(os.environ["IPMS_SCHEMA_PYTHON"])
    candidates.append(sys.executable)
    for name in ("python", "python3"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    for candidate in candidates:
        if run_command([candidate, "-c", "import pydantic"]).returncode == 0:
            return candidate
    return None


def run_third_party_tests() -> None:
    """模型、配置、存储、请求上下文与 HTTP 契约测试。

    需要一个装有 pydantic 的解释器；缺少对应第三方库的模块会自行跳过。
    """

    global _pydantic_python
    step("契约层测试（Pydantic / HTTP / 配置 / 存储）")

    chosen = _find_pydantic_python()
    if chosen is None:
        print("跳过：未找到安装 pydantic 的解释器。")
        print("      可用 IPMS_SCHEMA_PYTHON=<python 路径> 指定。")
        return

    _pydantic_python = chosen
    print(f"使用解释器：{chosen}")

    for pattern in THIRD_PARTY_TEST_MODULES:
        result = run_command(
            [
                chosen,
                "-m",
                "unittest",
                "discover",
                "-s",
                "backend/tests",
                "-t",
                "backend",
                "-p",
                pattern,
            ]
        )
        output = ((result.stderr or "") + (result.stdout or "")).strip().splitlines()
        summary = next((line for line in reversed(output) if line.startswith(("OK", "FAILED", "Ran "))), "")
        ran = next((line for line in reversed(output) if line.startswith("Ran ")), "")
        print(f" - {pattern:<28}{ran:<24}{summary}")
        if result.returncode != 0:
            failures.append(f"契约层测试失败：{pattern}")
            for line in output[-12:]:
                print(f"    {line}")


def _find_node() -> str | None:
    if os.environ.get("IPMS_NODE"):
        candidate = os.environ["IPMS_NODE"]
        if pathlib.Path(candidate).exists():
            return candidate
    for name in ("node", "node.exe"):
        found = shutil.which(name)
        if found:
            return found
    return None


def run_frontend_compile() -> None:
    """用本机可用的 @vue/compiler-sfc 与 tsc 实际编译前端。

    依赖 `.sfc` 沙箱（参见 docs/VERIFICATION.md），缺失时跳过并给出提示。
    """

    step("前端实际编译（SFC + TypeScript）")
    node = _find_node()
    if node is None:
        print("跳过：未找到 node，可用 IPMS_NODE=<node 路径> 指定。")
        return

    sandbox = ROOT / "frontend" / ".sfc" / "node_modules"
    compiler = sandbox / "@vue" / "compiler-sfc"
    if not compiler.exists():
        print("跳过：缺少 @vue/compiler-sfc 沙箱（见 docs/VERIFICATION.md）。")
        return

    result = run_command([node, ".sfc/check.mjs"], cwd=ROOT / "frontend")
    lines = (result.stdout or "").strip().splitlines()
    print(lines[-1] if lines else "(无输出)")
    if result.returncode != 0:
        for line in lines[-15:]:
            print(f" {line}")
        failures.append("Vue 单文件组件编译失败")
        return

    tsc_candidates = [
        ROOT / "frontend" / "node_modules" / "typescript" / "bin" / "tsc",
        sandbox / "typescript" / "bin" / "tsc",
    ]
    tsc = next((path for path in tsc_candidates if path.exists()), None)
    if tsc is None:
        print("跳过 TypeScript 检查：未找到 typescript。")
        return

    full_frontend = (ROOT / "frontend" / "node_modules" / "vue-router").exists()
    targets = ["src/env.d.ts", "src/main.ts"] if full_frontend else ["src/api.ts"]
    tsc_result = run_command(
        [
            node,
            str(tsc),
            "--ignoreConfig",
            "--noEmit",
            "--strict",
            "--target",
            "ES2022",
            "--module",
            "ESNext",
            "--moduleResolution",
            "Bundler",
            "--lib",
            "ES2022,DOM,DOM.Iterable",
            "--skipLibCheck",
            *targets,
        ],
        cwd=ROOT / "frontend",
    )
    if tsc_result.returncode != 0:
        print("TypeScript 检查未通过：")
        print((tsc_result.stdout or "").strip()[-1500:])
        failures.append("前端 TypeScript 检查失败")
    else:
        print(f"TypeScript 检查通过：{'、'.join(targets)}（strict）")


def run_pg_compat() -> None:
    """PostgreSQL 方言兼容性：编译 DDL 与查询，不需要服务器。"""

    step("PostgreSQL 方言兼容性（DDL + 查询编译）")
    python = os.environ.get("IPMS_LIVE_PYTHON") or os.environ.get("IPMS_SCHEMA_PYTHON") or sys.executable
    deps = os.environ.get("IPMS_DEPS")

    env = {}
    if deps and pathlib.Path(deps).exists():
        env["PYTHONPATH"] = os.pathsep.join([str(BACKEND), deps])

    probe = run_command([python, "-c", "import sqlalchemy"], extra_env=env)
    if probe.returncode != 0:
        print("跳过：该解释器未安装 SQLAlchemy（可用 IPMS_LIVE_PYTHON / IPMS_DEPS 指定）。")
        return

    result = run_command([python, str(ROOT / "scripts" / "pg_compat_check.py")], extra_env=env)
    lines = (result.stdout or "").strip().splitlines()
    print(lines[-1] if lines else "(无输出)")
    if result.returncode != 0:
        for line in lines[-20:]:
            print(f" {line}")
        failures.append("PostgreSQL 方言兼容性检查失败")
        return

    # 本机 alembic 可能未安装；backend/alembic 迁移目录会被误当成命名空间包，
    # 因此必须检查真实模块文件，而不是仅判断 import 是否成功。
    alembic_probe = run_command(
        [python, "-c", "import alembic, sys; sys.exit(0 if getattr(alembic, '__file__', None) else 1)"],
        extra_env=env,
    )
    if alembic_probe.returncode != 0:
        print("跳过 DDL 校验：该解释器未安装 Alembic（可用 IPMS_SCHEMA_PYTHON 指定）。")
        return

    ddl = run_command([python, str(ROOT / "scripts" / "pg_ddl_check.py")], extra_env=env)
    ddl_lines = (ddl.stdout or "").strip().splitlines()
    print(ddl_lines[-1] if ddl_lines else "(无输出)")
    if ddl.returncode != 0:
        for line in ddl_lines[-20:]:
            print(f" {line}")
        failures.append("PostgreSQL DDL 校验失败")


def run_live_api() -> None:
    """真实启动服务并跑主流程（需要 IPMS_LIVE=1 与 IPMS_DEPS 指向依赖目录）。"""

    step("端到端服务验证（真实 uvicorn + SQLite）")
    if os.environ.get("IPMS_LIVE") != "1":
        print("跳过：设置 IPMS_LIVE=1 可启用（需要 fastapi / sqlalchemy / uvicorn）。")
        return

    deps = os.environ.get("IPMS_DEPS")
    if not deps or not pathlib.Path(deps).exists():
        print("跳过：请用 IPMS_DEPS=<依赖目录> 指定含 fastapi/sqlalchemy/uvicorn 的目录。")
        return

    python = (
        os.environ.get("IPMS_LIVE_PYTHON")
        or os.environ.get("IPMS_SCHEMA_PYTHON")
        or sys.executable
    )
    env = {"PYTHONPATH": os.pathsep.join([str(BACKEND), deps])}
    result = run_command([python, str(ROOT / "scripts" / "live_api_check.py")], extra_env=env)
    lines = (result.stdout or "").strip().splitlines()
    print(lines[-1] if lines else "(无输出)")
    if result.returncode != 0:
        for line in lines[-25:]:
            print(f" {line}")
        failures.append("端到端服务验证失败")


def run_browser_check() -> None:
    """浏览器渲染验证：需要 dist 产物、Edge、以及可启动浏览器的权限。"""

    step("浏览器渲染验证（无头 Edge）")
    if os.environ.get("IPMS_BROWSER") != "1":
        print("跳过：设置 IPMS_BROWSER=1 可启用（需要 frontend/dist 与 Edge）。")
        return

    python = os.environ.get("IPMS_LIVE_PYTHON") or os.environ.get("IPMS_SCHEMA_PYTHON") or sys.executable
    deps = os.environ.get("IPMS_DEPS")
    env = {}
    if deps and pathlib.Path(deps).exists():
        env["PYTHONPATH"] = os.pathsep.join([str(BACKEND), deps])

    result = run_command([python, str(ROOT / "scripts" / "browser_check.py")], extra_env=env)
    lines = (result.stdout or "").strip().splitlines()
    print(lines[-1] if lines else "(无输出)")
    if result.returncode != 0:
        for line in lines[-20:]:
            print(f" {line}")
        failures.append("浏览器渲染验证失败")


def run_interactive_check() -> None:
    """浏览器交互验证：真实填写登录表单。需要完整权限与 Edge。"""

    step("浏览器交互验证（CDP 登录流程）")
    if os.environ.get("IPMS_INTERACTIVE") != "1":
        print("跳过：设置 IPMS_INTERACTIVE=1 可启用（需要 frontend/dist、Edge 与完整权限）。")
        return

    python = os.environ.get("IPMS_LIVE_PYTHON") or os.environ.get("IPMS_SCHEMA_PYTHON") or sys.executable
    deps = os.environ.get("IPMS_DEPS")
    env = {}
    if deps and pathlib.Path(deps).exists():
        env["PYTHONPATH"] = os.pathsep.join([str(BACKEND), deps])

    result = run_command([python, str(ROOT / "scripts" / "cdp_login_check.py")], extra_env=env)
    lines = (result.stdout or "").strip().splitlines()
    print(lines[-1] if lines else "(无输出)")
    if result.returncode != 0:
        for line in lines[-20:]:
            print(f" {line}")
        failures.append("浏览器交互验证失败")


def run_backend_tests(offline: bool) -> None:
    if offline:
        return
    step("后端测试")
    probe = run_command([sys.executable, "-c", "import pytest"])
    if probe.returncode != 0:
        print("未安装 pytest，已跳过。执行：cd backend && pip install -r requirements.txt")
        return
    result = run_command([sys.executable, "-m", "pytest", "-q"], cwd=BACKEND)
    print((result.stdout or "").strip()[-2000:])
    if result.returncode != 0:
        failures.append("后端测试失败")


def run_frontend_typecheck(offline: bool) -> None:
    if offline:
        return
    step("前端类型检查")
    if not (ROOT / "frontend" / "node_modules").exists():
        print("未安装前端依赖，已跳过。执行：cd frontend && pnpm install")
        return
    result = run_command(["pnpm", "run", "typecheck"], cwd=ROOT / "frontend")
    print((result.stdout or "").strip()[-2000:])
    if result.returncode != 0:
        failures.append("前端类型检查失败")


def main() -> int:
    parser = argparse.ArgumentParser(description="知识产权管理系统自检")
    parser.add_argument("--offline", action="store_true", help="只执行离线静态检查")
    args = parser.parse_args()

    compile_backend()
    check_backend_imports()
    check_frontend()
    run_model_check()
    run_api_audit()
    run_contract_check()
    run_domain_tests()
    run_third_party_tests()
    run_frontend_compile()
    run_pg_compat()
    run_live_api()
    run_browser_check()
    run_interactive_check()
    run_backend_tests(args.offline)
    run_frontend_typecheck(args.offline)

    print()
    if failures:
        print("校验未通过：")
        for item in failures:
            print(f" - {item}")
        return 1
    print("离线校验全部通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
