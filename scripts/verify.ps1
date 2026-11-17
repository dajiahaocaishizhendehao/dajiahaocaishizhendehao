# 一键离线/在线校验脚本
# 用法（仓库根目录）：pwsh -File scripts/verify.ps1
# 行为：始终执行离线静态检查；仅当依赖已安装时才执行 pytest 与前端类型检查。

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Find-Python {
    $candidates = @()
    if ($env:IPMS_PYTHON) { $candidates += $env:IPMS_PYTHON }
    $candidates += (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
    $candidates += (Get-Command python3 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) { return $candidate }
    }
    throw '未找到 Python 解释器。请安装 Python 3.12 或设置 IPMS_PYTHON。'
}

$python = Find-Python
Write-Host "使用 Python: $python"

Write-Host '== 1/4 Python 语法编译 =='
& $python -m compileall -q backend
if ($LASTEXITCODE -ne 0) { throw 'Python 编译失败' }

Write-Host '== 2/4 后端项目内导入解析 =='
$importCheck = @'
import ast, pathlib, sys
root = pathlib.Path("backend")
mods = {}
for p in root.rglob("*.py"):
    rel = p.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    mods[".".join(parts)] = p

def names(path):
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    out = set()
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(n.name)
        elif isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    out.add(t.id)
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            out.add(n.target.id)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                out.add(a.asname or a.name.split(".")[0])
    return out

errors = []
checked = 0
for name, path in sorted(mods.items()):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app"):
            base = node.module
            if base not in mods and not any(m.startswith(base + ".") for m in mods):
                errors.append(f"{path}: missing module {base}")
                continue
            exported = names(mods[base]) if base in mods else set()
            for a in node.names:
                checked += 1
                if a.name == "*" or a.name in exported or f"{base}.{a.name}" in mods:
                    continue
                errors.append(f"{path}: {base} missing {a.name}")
print(f"checked={checked} errors={len(errors)}")
for e in errors:
    print(" -", e)
sys.exit(1 if errors else 0)
'@
$importCheck | & $python -
if ($LASTEXITCODE -ne 0) { throw '后端导入解析失败' }

Write-Host '== 3/4 后端测试（依赖已安装时执行） =='
& $python -c "import pytest" 2>$null
if ($LASTEXITCODE -eq 0) {
    Push-Location backend
    try {
        & $python -m pytest -q
        if ($LASTEXITCODE -ne 0) { throw 'pytest 失败' }
    } finally {
        Pop-Location
    }
} else {
    Write-Warning '未安装 pytest，跳过测试。执行：cd backend; pip install -r requirements.txt'
}

Write-Host '== 4/4 前端类型检查（依赖已安装时执行） =='
if (Test-Path 'frontend/node_modules') {
    Push-Location frontend
    try {
        & pnpm run typecheck
        if ($LASTEXITCODE -ne 0) { throw '前端类型检查失败' }
    } finally {
        Pop-Location
    }
} else {
    Write-Warning '未安装前端依赖，跳过类型检查。执行：cd frontend; pnpm install'
}

Write-Host '校验完成。'
