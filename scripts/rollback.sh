#!/usr/bin/env bash
# 知识产权管理系统：回滚到服务器上的旧版本。
#
# 用法：
#   bash scripts/rollback.sh --list             # 查看服务器上的版本
#   bash scripts/rollback.sh                    # 回滚到当前版本的前一个版本
#   bash scripts/rollback.sh 20261116-1142      # 回滚到指定版本
#   bash scripts/rollback.sh --yes 20261116-1142
#
# 注意：本脚本只回滚代码和前端静态文件，不自动恢复数据库。
# 如果新版本执行过不兼容迁移，必须按 docs/DEPLOYMENT.md 第 9/10 节恢复备份。
#
# 可通过环境变量覆盖：
#   DEPLOY_HOST=10.20.0.18
#   DEPLOY_USER=root
#   DEPLOY_KEY=$HOME/.ssh/ipms_deploy
#   REMOTE_ROOT=/opt/ipms
#   SERVICE_NAME=ipms
#   NGINX_ROOT=/usr/share/nginx/ipms
#   BACKUP_SERVICE=ipms-backup.service

set -euo pipefail

DEPLOY_HOST=${DEPLOY_HOST:-10.20.0.18}
DEPLOY_USER=${DEPLOY_USER:-root}
DEPLOY_KEY=${DEPLOY_KEY:-$HOME/.ssh/ipms_deploy}
REMOTE_ROOT=${REMOTE_ROOT:-/opt/ipms}
SERVICE_NAME=${SERVICE_NAME:-ipms}
NGINX_ROOT=${NGINX_ROOT:-/usr/share/nginx/ipms}
BACKUP_SERVICE=${BACKUP_SERVICE:-ipms-backup.service}

TARGET=""
LIST=0
ASSUME_YES=0

usage() {
  cat <<'USAGE'
用法：bash scripts/rollback.sh [选项] [版本]

选项：
  --list          列出服务器上的版本，不执行回滚
  --yes, -y       跳过确认提示
  -h, --help      显示本帮助

不指定版本时，默认回滚到当前版本的前一个版本。
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --list) LIST=1 ;;
    --yes|-y) ASSUME_YES=1 ;;
    -h|--help) usage; exit 0 ;;
    --*)
      echo "错误：未知参数 $1" >&2
      usage
      exit 2
      ;;
    *)
      if [ -n "$TARGET" ]; then
        echo "错误：只能指定一个版本" >&2
        exit 2
      fi
      TARGET=$1
      ;;
  esac
  shift
done

if [ -n "$TARGET" ]; then
  TARGET=${TARGET##*/}
  case "$TARGET" in
    *[!0-9A-Za-z._-]*)
      echo "错误：版本号只能包含字母、数字、点、下划线、短横线：$TARGET" >&2
      exit 2
      ;;
  esac
fi

if command -v cygpath >/dev/null 2>&1; then
  DEPLOY_KEY=$(cygpath -w "$DEPLOY_KEY")
fi
[ -f "$DEPLOY_KEY" ] || { echo "错误：找不到 SSH 私钥：$DEPLOY_KEY" >&2; exit 2; }

SSH=(ssh -i "$DEPLOY_KEY" -o BatchMode=yes -o ConnectTimeout=10 "$DEPLOY_USER@$DEPLOY_HOST")
"${SSH[@]}" true || { echo "错误：SSH 连接失败" >&2; exit 2; }

mapfile -t NAMES < <("${SSH[@]}" "ls -1 '$REMOTE_ROOT'/releases 2>/dev/null | sort -r")
CURRENT=$("${SSH[@]}" "readlink -f '$REMOTE_ROOT/current'" 2>/dev/null || true)
CURRENT_NAME=${CURRENT##*/}

if [ "${#NAMES[@]}" -eq 0 ]; then
  echo "错误：服务器 $REMOTE_ROOT/releases 下没有版本目录" >&2
  exit 3
fi

if [ "$LIST" -eq 1 ]; then
  echo "服务器：$DEPLOY_USER@$DEPLOY_HOST"
  echo "当前版本：${CURRENT_NAME:-未知}"
  echo "可用版本："
  for name in "${NAMES[@]}"; do
    if [ "$name" = "$CURRENT_NAME" ]; then
      echo "  * $name (current)"
    else
      echo "    $name"
    fi
  done
  exit 0
fi

if [ -z "$TARGET" ]; then
  found_current=0
  for name in "${NAMES[@]}"; do
    if [ "$name" = "$CURRENT_NAME" ]; then
      found_current=1
      continue
    fi
    if [ "$found_current" -eq 1 ]; then
      TARGET=$name
      break
    fi
  done
  if [ -z "$TARGET" ]; then
    echo "错误：当前版本之前没有更旧的版本；请用 --list 查看并指定版本" >&2
    exit 3
  fi
fi

if [ "$TARGET" = "$CURRENT_NAME" ]; then
  echo "错误：目标版本就是当前版本：$TARGET" >&2
  exit 3
fi

"${SSH[@]}" "test -d '$REMOTE_ROOT/releases/$TARGET'" || {
  echo "错误：目标版本不存在：$TARGET" >&2
  exit 3
}

echo "当前版本：${CURRENT_NAME:-未知}"
echo "回滚目标：$TARGET"
echo "注意：只回滚代码和前端；数据库不会被自动恢复。"

if [ "$ASSUME_YES" -ne 1 ]; then
  read -r -p "确认回滚？输入 y 继续：" answer
  case "$answer" in
    y|Y|yes|YES) ;;
    *) echo "已取消"; exit 0 ;;
  esac
fi

"${SSH[@]}" "TARGET='$TARGET' REMOTE_ROOT='$REMOTE_ROOT' SERVICE_NAME='$SERVICE_NAME' NGINX_ROOT='$NGINX_ROOT' BACKUP_SERVICE='$BACKUP_SERVICE' bash -s" <<'REMOTE'
set -euo pipefail
cd /
TARGET_DIR="$REMOTE_ROOT/releases/$TARGET"
[ -d "$TARGET_DIR" ] || { echo "错误：目录不存在：$TARGET_DIR" >&2; exit 3; }

echo "==> 回滚前备份"
systemctl start "$BACKUP_SERVICE" || true

echo "==> 切换 current 到 $TARGET"
ln -sfn "$TARGET_DIR" "$REMOTE_ROOT/current"

echo "==> 恢复该版本的前端静态文件"
rm -rf "$NGINX_ROOT"/*
cp -r "$TARGET_DIR/frontend/dist/." "$NGINX_ROOT/"
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
  echo "错误：回滚后健康检查失败" >&2
  systemctl status "$SERVICE_NAME" --no-pager -l >&2 || true
  journalctl -u "$SERVICE_NAME" -n 60 --no-pager >&2 || true
  exit 5
fi

echo "回滚成功：$TARGET"
echo "current -> $(readlink -f "$REMOTE_ROOT/current")"
REMOTE

echo
echo "回滚完成。请浏览器强制刷新 http://$DEPLOY_HOST/ 验证。"
echo "如果新版本执行过不兼容数据库迁移，请按 docs/DEPLOYMENT.md 恢复数据库备份。"
