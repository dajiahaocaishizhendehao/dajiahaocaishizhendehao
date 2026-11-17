"""一键在本机启动知识产权管理系统。

做四件事：
1. 用 SQLite 建库并写入初始管理员（已存在则跳过）；
2. 启动后端 uvicorn；
3. 启动前端静态服务（托管 frontend/dist 并代理 /api）；
4. 打印访问地址与账号，按 Ctrl+C 退出。

用法：
    python scripts/run_local.py
    python scripts/run_local.py --port 5173 --api-port 8000

前置条件：
- 已执行 `vite build` 生成 frontend/dist；
- 运行环境能 import fastapi / sqlalchemy / uvicorn（本机可用依赖目录）。
"""

from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
DIST = ROOT / "frontend" / "dist"

DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "Admin@12345"


def prepare_paths() -> None:
    """把后端与（可选的）依赖目录加入模块搜索路径。

    设置 IPMS_DEPS 指向一个已装有 fastapi/sqlalchemy/uvicorn 的目录，
    即可在没有 pip 安装的情况下运行。
    """

    sys.path.insert(0, str(BACKEND))
    deps = os.environ.get("IPMS_DEPS")
    if deps and pathlib.Path(deps).exists():
        sys.path.insert(0, deps)
        os.environ["PYTHONPATH"] = os.pathsep.join(
            [str(BACKEND), deps, os.environ.get("PYTHONPATH", "")]
        ).strip(os.pathsep)
    else:
        os.environ["PYTHONPATH"] = os.pathsep.join(
            [str(BACKEND), os.environ.get("PYTHONPATH", "")]
        ).strip(os.pathsep)


def ensure_database(db_url: str) -> None:
    os.environ["DATABASE_URL"] = db_url

    from app import security
    from app.database import Base, SessionLocal, get_engine
    from app.models import User, UserRole
    from sqlalchemy import select

    engine = get_engine()
    Base.metadata.create_all(engine)
    with SessionLocal(bind=engine) as db:
        exists = db.scalar(select(User).where(User.username == DEFAULT_USERNAME))
        if exists is None:
            db.add(
                User(
                    username=DEFAULT_USERNAME,
                    display_name="系统管理员",
                    password_hash=security.hash_password(DEFAULT_PASSWORD),
                    role=UserRole.ADMIN,
                )
            )
            db.commit()
            print(f"已创建管理员账号：{DEFAULT_USERNAME} / {DEFAULT_PASSWORD}")
        else:
            print(f"复用已有管理员账号：{DEFAULT_USERNAME}")
    engine.dispose()


def wait_health(base: str, timeout: float = 40.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base}/health", timeout=3) as response:
                if response.status == 200:
                    return True
        except OSError:
            time.sleep(0.4)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="本机启动知识产权管理系统")
    parser.add_argument("--port", type=int, default=5173, help="前端端口")
    parser.add_argument("--api-port", type=int, default=8000, help="后端端口")
    parser.add_argument("--db", default=str(BACKEND / "var" / "ipms.db"), help="SQLite 文件路径")
    args = parser.parse_args()

    if not (DIST / "index.html").exists():
        print("缺少前端构建产物 frontend/dist，请先执行：")
        print("  cd frontend && node node_modules/vite/bin/vite.js build")
        return 1

    prepare_paths()

    db_path = pathlib.Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    print(f"数据库：{db_path}")
    ensure_database(db_url)

    api_base = f"http://127.0.0.1:{args.api_port}"
    env = dict(os.environ)
    env["DATABASE_URL"] = db_url
    env["PYTHONPATH"] = os.pathsep.join([str(BACKEND), env.get("PYTHONPATH", "")]).strip(os.pathsep)

    backend = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(args.api_port),
            "--log-level",
            "info",
        ],
        cwd=str(BACKEND),
        env=env,
    )

    frontend = subprocess.Popen(
        [
            sys.executable,
            str(ROOT / "scripts" / "serve_local.py"),
            "--dir",
            str(DIST),
            "--port",
            str(args.port),
            "--api",
            api_base,
        ],
        env=env,
    )

    try:
        if not wait_health(api_base):
            print("后端未能在预期时间内启动，请查看上方日志。")
            return 1

        print("")
        print("=" * 56)
        print(f"  前端地址：http://127.0.0.1:{args.port}")
        print(f"  接口文档：{api_base}/docs")
        print(f"  登录账号：{DEFAULT_USERNAME} / {DEFAULT_PASSWORD}")
        print("  按 Ctrl+C 停止服务")
        print("=" * 56)
        print("")

        while True:
            if backend.poll() is not None:
                print("后端进程已退出。")
                return 1
            if frontend.poll() is not None:
                print("前端进程已退出。")
                return 1
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n正在停止…")
        return 0
    finally:
        for process in (frontend, backend):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
