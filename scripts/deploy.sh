#!/usr/bin/env bash
# 知识产权管理系统：本机打包并发布到服务器。
#
# 用法：
#   bash scripts/deploy.sh                 # 跑测试、构建、打包并部署
#   bash scripts/deploy.sh --skip-tests    # 跳过本地 pytest
#   bash scripts/deploy.sh --skip-build    # 使用现有 frontend/dist
#   bash scripts/deploy.sh --version 20261117-0900
#
# 可通过环境变量覆盖：
#   DEPLOY_HOST=10.20.0.18
#   DEPLOY_USER=root
#   DEPLOY_KEY=$HOME/.ssh/ipms_deploy
#   REMOTE_ROOT=/opt/ipms
#   SERVICE_NAME=ipms
#   NGINX_ROOT=/usr/share/nginx/ipms
#   ENV_FILE=/etc/ipms/ipms.env
#   VENV=/opt/ipms/venv
#   PIP_INDEX_URL=https://repo.huaweicloud.com/repository/pypi/simple
#
# 前置条件：本机可用 ssh/scp/tar/node；服务器已按 docs/DEPLOYMENT.md 部署。

set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
DEPLOY_HOST=${DEPLOY_HOST:-10.20.0.18}
DEPLOY_USER=${DEPLOY_USER:-root}
DEPLOY_KEY=${DEPLOY_KEY:-$HOME/.ssh/ipms_deploy}
REMOTE_ROOT=${REMOTE_ROOT:-/opt/ipms}
SERVICE_NAME=${SERVICE_NAME:-ipms}
NGINX_ROOT=${NGINX_ROOT:-/usr/share/nginx/ipms}
ENV_FILE=${ENV_FILE:-/etc/ipms/ipms.env}
VENV=${VENV:-/opt/ipms/venv}
PIP_INDEX_URL=${PIP_INDEX_URL:-https://repo.huaweicloud.com/repository/pypi/simple}
BACKUP_SERVICE=${BACKUP_SERVICE:-ipms-backup.service}

SKIP_TESTS=0
SKIP_BUILD=0
VERSION=""

usage() {
  cat <<'USAGE'
用法：bash scripts/deploy.sh [选项]

选项：
  --skip-tests          跳过本地 pytest
  --skip-build          跳过前端构建，使用现有 frontend/dist
  --version <版本>      指定版本号，默认按当前时间生成
  -h, --help            显示本帮助

环境变量：
  DEPLOY_HOST           服务器地址，默认 10.20.0.18
  DEPLOY_USER           SSH 用户，默认 root
  DEPLOY_KEY            SSH 私钥，默认 $HOME/.ssh/ipms_deploy
  REMOTE_ROOT           服务器发布根目录，默认 /opt/ipms
  NGINX_ROOT            Nginx 静态目录，默认 /usr/share/nginx/ipms
  SERVICE_NAME          systemd 服务名，默认 ipms
  PIP_INDEX_URL         服务器 pip 镜像
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --skip-tests) SKIP_TESTS=1 ;;
    --skip-build) SKIP_BUILD=1 ;;
    --version)
      VERSION=${2:-}
      if [ -z "$VERSION" ]; then
        echo "错误：--version 缺少参数" >&2
        exit 2
      fi
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "错误：未知参数 $1" >&2
      usage
      exit 2
      ;;
  esac
  shift
done

if [ -z "$VERSION" ]; then
  VERSION=$(date +%Y%m%d-%H%M%S)
fi
case "$VERSION" in
  *[!0-9A-Za-z._-]*)
    echo "错误：版本号只能包含字母、数字、点、下划线、短横线：$VERSION" >&2
    exit 2
    ;;
esac

if command -v cygpath >/dev/null 2>&1; then
  DEPLOY_KEY=$(cygpath -w "$DEPLOY_KEY")
fi

for bin in ssh scp tar; do
  command -v "$bin" >/dev/null 2>&1 || { echo "错误：本机缺少命令 $bin" >&2; exit 2; }
done
[ -f "$DEPLOY_KEY" ] || { echo "错误：找不到 SSH 私钥：$DEPLOY_KEY" >&2; exit 2; }

SSH=(ssh -i "$DEPLOY_KEY" -o BatchMode=yes -o ConnectTimeout=10 "$DEPLOY_USER@$DEPLOY_HOST")
SCP=(scp -i "$DEPLOY_KEY" -o BatchMode=yes)

echo "目标服务器：$DEPLOY_USER@$DEPLOY_HOST"
echo "版本：$VERSION"
"${SSH[@]}" true || { echo "错误：SSH 连接失败，请先确认密钥和网络" >&2; exit 2; }

# 本地测试
if [ "$SKIP_TESTS" -eq 0 ]; then
  if [ -x "$ROOT/backend/.venv/Scripts/python.exe" ]; then
    PYTEST_PY="$ROOT/backend/.venv/Scripts/python.exe"
  elif [ -x "$ROOT/backend/.venv/bin/python" ]; then
    PYTEST_PY="$ROOT/backend/.venv/bin/python"
  else
    echo "错误：未找到 backend/.venv，无法运行 pytest；可加 --skip-tests" >&2
    exit 2
  fi
  echo "==> 运行后端测试"
  (cd "$ROOT/backend" && "$PYTEST_PY" -m pytest -q)
fi

# 本地构建
if [ "$SKIP_BUILD" -eq 0 ]; then
  echo "==> 构建前端"
  command -v node >/dev/null 2>&1 || { echo "错误：本机缺少命令 node" >&2; exit 2; }
  [ -f "$ROOT/frontend/node_modules/vite/bin/vite.js" ] || {
    echo "错误：缺少 frontend/node_modules，请先安装前端依赖" >&2
    exit 2
  }
  (cd "$ROOT/frontend" && node node_modules/vite/bin/vite.js build)
else
  [ -f "$ROOT/frontend/dist/index.html" ] || {
    echo "错误：frontend/dist 不存在，不能使用 --skip-build" >&2
    exit 2
  }
fi

# 打包
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT
PKG="$TMP_DIR/ipms-$VERSION.tar.gz"
echo "==> 生成发布包"
tar -czf "$PKG" -C "$ROOT" \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  backend/app \
  backend/alembic \
  backend/alembic.ini \
  backend/requirements.txt \
  backend/requirements-ocr.txt \
  backend/tools \
  backend/.env.example \
  frontend/dist

echo "==> 上传发布包"
"${SCP[@]}" "$PKG" "$DEPLOY_USER@$DEPLOY_HOST:/tmp/ipms-$VERSION.tar.gz"

# 远程部署
echo "==> 服务器部署"
"${SSH[@]}" "VERSION='$VERSION' REMOTE_ROOT='$REMOTE_ROOT' SERVICE_NAME='$SERVICE_NAME' NGINX_ROOT='$NGINX_ROOT' ENV_FILE='$ENV_FILE' VENV='$VENV' PIP_INDEX_URL='$PIP_INDEX_URL' BACKUP_SERVICE='$BACKUP_SERVICE' PUBLIC_HOST='$DEPLOY_HOST' bash -s" <<'REMOTE'
set -euo pipefail
cd /

RELEASE="$REMOTE_ROOT/releases/$VERSION"
if [ -e "$RELEASE" ]; then
  echo "错误：版本目录已存在：$RELEASE" >&2
  exit 3
fi

echo "==> 发布前备份"
systemctl start "$BACKUP_SERVICE"
if [ "$(systemctl show -p Result --value "$BACKUP_SERVICE")" != "success" ]; then
  echo "错误：备份失败，停止部署" >&2
  journalctl -u "$BACKUP_SERVICE" -n 30 --no-pager >&2 || true
  exit 4
fi

echo "==> 解压到 $RELEASE"
mkdir -p "$RELEASE"
tar -xzf "/tmp/ipms-$VERSION.tar.gz" -C "$RELEASE"
chown -R ipms:ipms "$RELEASE"

echo "==> 保存发布包到 $REMOTE_ROOT/packages"
mkdir -p "$REMOTE_ROOT/packages"
cp -f "/tmp/ipms-$VERSION.tar.gz" "$REMOTE_ROOT/packages/"
chown root:root "$REMOTE_ROOT/packages/ipms-$VERSION.tar.gz"
chmod 640 "$REMOTE_ROOT/packages/ipms-$VERSION.tar.gz"

echo "==> 安装后端依赖"
runuser -u ipms -- env PIP_DEFAULT_TIMEOUT=60 "$VENV/bin/pip" install \
  -i "$PIP_INDEX_URL" -r "$RELEASE/backend/requirements.txt"

echo "==> 执行数据库迁移"
runuser -u ipms -- bash -c "set -a; . '$ENV_FILE'; set +a; cd '$RELEASE/backend' && '$VENV/bin/alembic' upgrade head"

echo "==> 切换 current 软链接"
ln -sfn "$RELEASE" "$REMOTE_ROOT/current"

echo "==> 更新 Nginx 静态文件"
rm -rf "$NGINX_ROOT"/*
cp -r "$REMOTE_ROOT/current/frontend/dist/." "$NGINX_ROOT/"
chown -R root:root "$NGINX_ROOT"
chmod -R 755 "$NGINX_ROOT"

echo "==> 重启服务"
systemctl restart "$SERVICE_NAME"
nginx -t
systemctl reload nginx

echo "==> 健康检查"
ok=0
for _ in $(seq 1 20); do
  if curl -fsS --max-time 5 http://127.0.0.1:8000/health >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 1
done
if [ "$ok" -ne 1 ]; then
  echo "错误：后端健康检查失败。当前 current 已指向 $RELEASE" >&2
  systemctl status "$SERVICE_NAME" --no-pager -l >&2 || true
  journalctl -u "$SERVICE_NAME" -n 60 --no-pager >&2 || true
  exit 5
fi

site_code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 -H "Host: $PUBLIC_HOST" http://127.0.0.1/)
if [ "$site_code" != "200" ]; then
  echo "错误：站点首页返回 $site_code（期望 200）" >&2
  exit 6
fi

rm -f "/tmp/ipms-$VERSION.tar.gz"
echo "部署成功：$VERSION"
echo "current -> $(readlink -f "$REMOTE_ROOT/current")"
REMOTE

echo
echo "完成。请浏览器打开 http://$DEPLOY_HOST/ 验证登录和工作台。"
echo "如需回滚：bash scripts/rollback.sh --list"
