@echo off
chcp 65001 >nul
setlocal

REM 一键启动知识产权管理系统（本机）
REM
REM 如果需要使用本机已有的依赖目录（未执行 pip install 的情况），
REM 先把 IPMS_DEPS 设为该目录，例如：
REM   set IPMS_DEPS=D:\path\to\site-packages
REM
REM 默认端口：前端 5173，后端 8000。

cd /d "%~dp0.."

if defined IPMS_DEPS (
  echo 使用依赖目录: %IPMS_DEPS%
) else (
  echo 未设置 IPMS_DEPS，将使用当前 Python 环境已安装的依赖。
)

python scripts\run_local.py %*

if errorlevel 1 (
  echo.
  echo 启动失败。常见原因：
  echo   1. 未安装 fastapi/sqlalchemy/uvicorn —— 可用 IPMS_DEPS 指向依赖目录
  echo   2. 端口被占用 —— 用 --port 与 --api-port 更换端口
  echo   3. 缺少 frontend/dist —— 先执行前端构建
  pause
)

endlocal
