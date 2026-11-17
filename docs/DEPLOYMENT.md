# 部署指南（openEuler 22.03 · PostgreSQL · 内网）

本文档按实际服务器条件编写：

- 服务器：openEuler 22.03 SP4，x86_64，内网 IP `10.20.0.18`；
- 数据库：PostgreSQL；
- 访问方式：公司内网，不直接暴露公网；
- 运行方式：Nginx 托管前端静态文件并反向代理 FastAPI，systemd 管理后端进程。

> 这些命令**未在 openEuler 服务器上实际执行过**（本机是 Windows 开发环境）。首次部署请逐条执行并核对输出；特别是 SELinux、PostgreSQL 初始化、防火墙三处，不同镜像的默认值可能不同。

## 1. 发布包内容

发布包只包含运行所需内容：

```text
backend/app/            后端代码
backend/alembic/        数据库迁移
backend/alembic.ini
backend/requirements.txt
backend/tools/          创建管理员等运维工具
backend/.env.example    配置模板（不要放真实密码）
frontend/dist/          前端构建产物
```

不要把以下内容打进发布包：`.venv`、`node_modules`、`backend/var`、测试文件、截图、`__pycache__`、`.pytest_cache`、`.edge-*`、本地数据库。

## 2. 本机打包

先构建前端（前端产物已在本地验证；若代码有改动，重新执行）：

```bash
cd "/d/DS-workSpace/Patent Management System/frontend"
node node_modules/vite/bin/vite.js build
```

在仓库根目录生成发布包：

```bash
cd "/d/DS-workSpace/Patent Management System"
VERSION=$(date +%Y%m%d-%H%M)
tar -czf "ipms-$VERSION.tar.gz" \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  backend/app \
  backend/alembic \
  backend/alembic.ini \
  backend/requirements.txt \
  backend/tools \
  backend/.env.example \
  frontend/dist
```

上传到服务器：

```bash
scp ipms-<版本>.tar.gz root@10.20.0.18:/tmp/
```

## 3. 服务器准备（openEuler）

当前服务器实测：openEuler 22.03 SP4、Python 3.9.9、SELinux Disabled、firewalld 运行中、80/8000/5432 均未占用、磁盘剩余 46 GB、可访问 PyPI。

### 3.1 安装 Python 3.10+

服务器自带的 Python 3.9.9 **不满足要求**：代码大量使用 `str | None` 类型注解，需要 Python 3.10 及以上；项目只在 Python 3.12.10 上测试过。

**不要替换或卸载系统 `python3`**，firewalld 和 dnf 依赖它。单独安装到 `/opt/python3.12`。

先看 openEuler 仓库是否直接提供新版本：

```bash
dnf list available 'python3.1*'
```

本次服务器实测该命令返回 “No matching Packages”，因此按下面的源码方式安装了 Python 3.12.10。如果能看到 `python3.10`、`python3.11` 或 `python3.12`，也可以直接安装对应包，并把下文的 `/opt/python3.12/bin/python3.12` 换成实际路径。

从源码编译（服务器访问 python.org 很慢时，使用华为云镜像；本次实际使用镜像下载）：

```bash
dnf install -y gcc make openssl-devel bzip2-devel libffi-devel zlib-devel xz-devel \
  sqlite-devel readline-devel ncurses-devel

cd /usr/local/src
curl -fL -o Python-3.12.10.tgz https://repo.huaweicloud.com/python/3.12.10/Python-3.12.10.tgz
tar -xzf Python-3.12.10.tgz
cd Python-3.12.10
./configure --prefix=/opt/python3.12 --with-ensurepip=install
make -j"$(nproc)"
make altinstall

/opt/python3.12/bin/python3.12 --version
```

### 3.2 安装其余依赖

```bash
dnf install -y nginx postgresql-server postgresql-contrib policycoreutils tar curl
```

如果提示找不到 `postgresql-server`，先执行 `dnf search postgresql` 确认本仓库的包名，不要直接跳过数据库安装。

创建运行用户和目录：

```bash
useradd --system --create-home --home-dir /opt/ipms --shell /sbin/nologin ipms
mkdir -p /opt/ipms/releases /var/lib/ipms/storage /etc/ipms /var/backups/ipms /usr/share/nginx/ipms
chown -R ipms:ipms /opt/ipms /var/lib/ipms
chown root:ipms /etc/ipms
chmod 755 /opt/ipms /opt/ipms/releases /usr/share/nginx/ipms
chmod 750 /var/lib/ipms /var/lib/ipms/storage /etc/ipms
```

说明：

- 代码放 `/opt/ipms/releases/<版本>`，用 `/opt/ipms/current` 软链接切换版本；
- 发布包归档放 `/opt/ipms/packages/ipms-<版本>.tar.gz`；
- 上传文件持久化在 `/var/lib/ipms/storage`，不随发布包替换；
- 配置放 `/etc/ipms/ipms.env`，与代码分离；
- 前端静态文件放 `/usr/share/nginx/ipms`，避免 `/opt` 在 SELinux 下的读取问题。

如果服务器之后**不能访问外网 / PyPI**，需要改为离线 wheel 包部署；当前预检显示可以访问 PyPI。

### 3.3 EasyOCR（可选，证书扫描件 OCR）

本服务器 CPU 不支持 AVX2/FBGEMM；必须用 CPU 版 PyTorch，并关闭 EasyOCR 的量化 LSTM，否则识别时会 `Illegal instruction`。代码已在 `app/extraction.py` 中设置 `quantize=False`。

创建模型目录：

```bash
mkdir -p /opt/ipms/.EasyOCR/model /opt/ipms/.EasyOCR/user_network
chown -R ipms:ipms /opt/ipms/.EasyOCR
chmod 750 /opt/ipms/.EasyOCR /opt/ipms/.EasyOCR/model /opt/ipms/.EasyOCR/user_network
```

安装依赖（使用独立的 OCR requirements，避免影响主依赖）：

```bash
runuser -u ipms -- /opt/ipms/venv/bin/pip install \
  -r /opt/ipms/current/backend/requirements-ocr.txt
```

准备模型文件。可以联网下载：

```bash
runuser -u ipms -- env HOME=/opt/ipms /opt/ipms/venv/bin/python -c \
  "import easyocr; easyocr.Reader(['ch_sim','en'], gpu=False, download_enabled=True, quantize=False)"
```

也可以把已有的模型直接放到：

```text
/opt/ipms/.EasyOCR/model/craft_mlt_25k.pth
/opt/ipms/.EasyOCR/model/zh_sim_g2.pth
```

并确保权限：

```bash
chown ipms:ipms /opt/ipms/.EasyOCR/model/*.pth
chmod 640 /opt/ipms/.EasyOCR/model/*.pth
```

应用运行时的 `HOME` 是 `/opt/ipms`，所以默认模型路径就是 `/opt/ipms/.EasyOCR/model`。`download_enabled=False` 时不会再联网；缺少模型会明确报错。

## 4. PostgreSQL（openEuler）

初始化并启动：

```bash
/usr/bin/postgresql-setup --initdb
systemctl enable --now postgresql
systemctl status postgresql --no-pager
psql --version
```

创建数据库账号（示例密码必须替换为强密码）：

```bash
sudo -u postgres psql
```

```sql
CREATE USER ipms WITH PASSWORD '<强密码>';
CREATE DATABASE ipms OWNER ipms;
\q
```

确认 `pg_hba.conf` 允许本机 TCP 密码登录：

```bash
grep -vE '^\s*#|^\s*$' /var/lib/pgsql/data/pg_hba.conf
```

openEuler 的 PostgreSQL 13 默认是 `host ... ident` + `password_encryption=md5`，本次实测会导致应用连接报 “password authentication failed”。需要同时处理两处：

```bash
# 1) 把 127.0.0.1 / ::1 的 host 规则从 ident 改为 scram-sha-256
HBA=/var/lib/pgsql/data/pg_hba.conf
cp -a "$HBA" "$HBA.bak-$(date +%Y%m%d%H%M)"
sed -i -E '/^host[[:space:]]+all[[:space:]]+all[[:space:]]+(127\.0\.0\.1\/32|::1\/128)[[:space:]]+ident/s/ident$/scram-sha-256/' "$HBA"
systemctl reload postgresql

# 2) 确认密码加密方式；如果是 md5，则用 scram 重设应用账号密码
sudo -u postgres psql -tAc "show password_encryption;"
sudo -u postgres psql -c "SET password_encryption='scram-sha-256'; ALTER USER ipms WITH PASSWORD '<强密码>';"
```

需要存在类似下面这一行：

```text
host    all             all             127.0.0.1/32            scram-sha-256
```

验证登录：

```bash
psql "postgresql://ipms:<强密码>@127.0.0.1:5432/ipms" -c "select version();"
```

默认只监听本机；本次按用户要求同时监听 `10.20.0.18`，并只对三个受控内网网段放行 5432。后端仍通过 `127.0.0.1` 连接。

## 5. 部署后端

解压发布包：

```bash
VERSION=<版本号>
mkdir -p /opt/ipms/releases/$VERSION
tar -xzf /tmp/ipms-$VERSION.tar.gz -C /opt/ipms/releases/$VERSION
chown -R ipms:ipms /opt/ipms/releases/$VERSION
ln -sfn /opt/ipms/releases/$VERSION /opt/ipms/current
```

创建共享虚拟环境并安装依赖：

```bash
sudo -u ipms /opt/python3.12/bin/python3.12 -m venv /opt/ipms/venv
sudo -u ipms /opt/ipms/venv/bin/pip install --upgrade pip
sudo -u ipms /opt/ipms/venv/bin/pip install -r /opt/ipms/releases/$VERSION/backend/requirements.txt
```

创建 `/etc/ipms/ipms.env`（密码中的特殊字符要做 URL 编码）：

```ini
DATABASE_URL=postgresql+psycopg://ipms:<URL编码后的密码>@127.0.0.1:5432/ipms
ENVIRONMENT=production
STORAGE_ROOT=/var/lib/ipms/storage
SESSION_TTL_MINUTES=720
DUE_SOON_DAYS=30
MAX_UPLOAD_BYTES=52428800
```

```bash
chown root:ipms /etc/ipms/ipms.env
chmod 640 /etc/ipms/ipms.env
```

执行数据库迁移（必须使用同一份环境变量）：

```bash
sudo -u ipms bash -c 'set -a; . /etc/ipms/ipms.env; set +a; \
  cd /opt/ipms/current/backend && \
  /opt/ipms/venv/bin/alembic upgrade head'
```

创建首个管理员（密码至少 8 位，创建后立即登录修改）：

```bash
sudo -u ipms bash -c 'set -a; . /etc/ipms/ipms.env; set +a; \
  cd /opt/ipms/current/backend && \
  /opt/ipms/venv/bin/python -m tools.create_admin \
  --username admin --password "<初始强密码>" --name "系统管理员"'
```

## 6. systemd 服务

创建 `/etc/systemd/system/ipms.service`：

```ini
[Unit]
Description=IPMS FastAPI service
After=network.target postgresql.service

[Service]
Type=simple
User=ipms
Group=ipms
WorkingDirectory=/opt/ipms/current/backend
EnvironmentFile=/etc/ipms/ipms.env
ExecStart=/opt/ipms/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now ipms
systemctl status ipms --no-pager
curl -s http://127.0.0.1:8000/health
```

预期返回：`{"status":"ok","app":"知识产权管理系统"}`。

说明：先使用 1 个 worker。材料识别使用进程内线程池，增加 worker 前需要评估重复任务与内存占用，当前未做多 worker 验证。

## 7. Nginx 反向代理（openEuler）

把前端产物复制到 Nginx 目录（SELinux 默认标签正确）：

```bash
rm -rf /usr/share/nginx/ipms/*
cp -r /opt/ipms/current/frontend/dist/. /usr/share/nginx/ipms/
chown -R root:root /usr/share/nginx/ipms
chmod -R 755 /usr/share/nginx/ipms
```

创建 `/etc/nginx/conf.d/ipms.conf`：

```nginx
server {
    listen 80;
    server_name 10.20.0.18;

    root /usr/share/nginx/ipms;
    index index.html;
    client_max_body_size 60m;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
    }

    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
        try_files $uri =404;
    }

    location / {
        try_files $uri $uri/ /index.html;
        add_header Cache-Control "no-cache";
    }
}
```

`server_name` 必须写实际访问使用的 IP 或域名。openEuler 自带的 `nginx.conf` 已有一个 `server_name _; listen 80;` 默认站点，如果这里也写 `_`，`nginx -t` 会报 conflicting server name，且请求可能落到默认站点；本次使用 `10.20.0.18` 解决。

如果 openEuler 自带的 `nginx.conf` 没有包含 `conf.d/*.conf`，在 `http {}` 内补上：

```nginx
include /etc/nginx/conf.d/*.conf;
```

检查并启动：

```bash
nginx -t
systemctl enable --now nginx
systemctl reload nginx
```

### SELinux

当前服务器 `getenforce` 结果为 `Disabled`，本节命令可以跳过；如果以后启用 SELinux，再执行：

```bash
# Nginx 反向代理到 127.0.0.1:8000 必需
setsebool -P httpd_can_network_connect 1

# 确认静态目录标签
restorecon -Rv /usr/share/nginx/ipms
```

如果访问页面报 403，查看 `/var/log/audit/audit.log` 或 `journalctl -u nginx`，不要直接 `setenforce 0` 了事。

## 8. 内网访问与首次验证

只对内网网段放行 80 端口（按实际网段替换）：

```bash
firewall-cmd --permanent --add-rich-rule='rule family="ipv4" source address="10.20.0.0/24" port port="80" protocol="tcp" accept'
firewall-cmd --permanent --add-rich-rule='rule family="ipv4" source address="172.20.0.0/22" port port="80" protocol="tcp" accept'
firewall-cmd --permanent --add-rich-rule='rule family="ipv4" source address="192.168.203.0/24" port port="80" protocol="tcp" accept'
firewall-cmd --reload
firewall-cmd --list-all
```

本次实际访问客户端出现过两个网段：`172.20.0.0/22` 和 `192.168.203.0/24`（笔记本切换 Wi-Fi 后 DHCP 地址变化），服务器自身在 `10.20.0.0/24`，三条规则都保留。不要只按服务器 IP 所在网段放行，否则其他内网客户端会被拦截；如果客户端地址再变化，需要补充对应网段或为其分配固定 IP。

按用户要求允许 Navicat 直连数据库时，再对同三个内网网段放行 5432：

```bash
firewall-cmd --permanent --add-rich-rule='rule family="ipv4" source address="10.20.0.0/24" port port="5432" protocol="tcp" accept'
firewall-cmd --permanent --add-rich-rule='rule family="ipv4" source address="172.20.0.0/22" port port="5432" protocol="tcp" accept'
firewall-cmd --permanent --add-rich-rule='rule family="ipv4" source address="192.168.203.0/24" port port="5432" protocol="tcp" accept'
firewall-cmd --reload
```

直连数据库意味着内网客户端可以访问 5432。必须保持 PostgreSQL 密码为强密码、只对受控网段放行，并优先使用只读账号做查看；不要对公网或不受控网段开放 5432。

如果 `firewalld` 默认已放行 `http` 服务，先移除，避免整个网络可访问：

```bash
firewall-cmd --permanent --remove-service=http
firewall-cmd --reload
```

不要放行 8000；它只监听本机。5432 只按上面的内网来源规则放行。

依次验证：

1. `curl -s http://127.0.0.1:8000/health` 返回 `status: ok`；
2. `curl -I http://10.20.0.18/` 返回 200，且页面引用 `/assets/index-*.js`；
3. 浏览器打开 `http://10.20.0.18/`，用管理员账号登录；
4. 新建一条测试档案，上传一份材料，执行下载与识别；
5. 查看“系统管理 → 操作日志”，确认登录、新建、上传、下载都有记录；
6. 执行一次数据库备份与恢复演练（见第 9 节）。

## 9. 备份

本次已配置 systemd 定时备份，每天 02:00 执行（随机延迟 15 分钟），保留 14 天：

- 脚本：`/usr/local/sbin/ipms-backup.sh`
- 服务：`/etc/systemd/system/ipms-backup.service`
- 定时器：`/etc/systemd/system/ipms-backup.timer`
- 备份目录：`/var/backups/ipms`
- 文件命名：`db-YYYYmmdd-HHMMSS.dump`、`storage-YYYYmmdd-HHMMSS.tar.gz`

脚本会：

1. 检查备份目录至少剩余 2 GiB；
2. 用 `pg_dump -Fc` 备份数据库，并检查文件非空、`pg_restore -l` 可读取；
3. 打包 `/var/lib/ipms/storage`，并检查 tar 可读取；
4. 备份文件权限设为 600；
5. 删除 14 天前的同类备份。

查看和手动执行：

```bash
systemctl list-timers ipms-backup.timer --no-pager
systemctl start ipms-backup.service
journalctl -u ipms-backup.service -n 50 --no-pager
ls -lh /var/backups/ipms
```

数据库与上传文件的一致性：应用采用逻辑删除且保留旧文件，备份期间的数据库快照不会引用“尚未打包”的文件；如果将来改为物理删除文件，备份窗口内必须暂停上传或停服务。

恢复前先停服务：

```bash
systemctl stop ipms
sudo -u postgres pg_restore --clean --if-exists -d ipms /var/backups/ipms/db-<日期>.dump
tar -xzf /var/backups/ipms/storage-<日期>.tar.gz -C /var/lib/ipms
chown -R ipms:ipms /var/lib/ipms/storage
systemctl start ipms
```

`pg_dump` 不包含 PostgreSQL 角色和密码。换新机器恢复时，必须先创建 `ipms` 角色和空库，再执行恢复；否则对象属主和连接都会失败。

恢复演练建议每月做一次：把 dump 恢复到一个临时库，核对表数量与 `alembic_version`，再删除临时库，不要直接覆盖生产库。

## 10. 版本升级与回滚

### 发布脚本

本机仓库提供两个脚本，均在**本机**执行（通过 SSH 操作服务器），需要可用的 SSH 私钥：

```bash
# 发布：默认跑 pytest、构建前端、打包、上传、备份、迁移、切版本、重启、健康检查
bash scripts/deploy.sh

# 跳过测试或构建
bash scripts/deploy.sh --skip-tests
bash scripts/deploy.sh --skip-build

# 指定版本
bash scripts/deploy.sh --version 20261117-0900

# 查看服务器版本
bash scripts/rollback.sh --list

# 回滚到当前版本的前一个版本
bash scripts/rollback.sh

# 回滚到指定版本
bash scripts/rollback.sh 20261116-1142
```

默认配置：

```text
DEPLOY_HOST=10.20.0.18
DEPLOY_USER=root
DEPLOY_KEY=$HOME/.ssh/ipms_deploy
REMOTE_ROOT=/opt/ipms
SERVICE_NAME=ipms
NGINX_ROOT=/usr/share/nginx/ipms
ENV_FILE=/etc/ipms/ipms.env
VENV=/opt/ipms/venv
```

`deploy.sh` 会拒绝覆盖已存在的版本目录，并在迁移前执行一次自动备份；健康检查失败会保留新版本目录并提示回滚。`rollback.sh` 只回滚代码和前端静态文件，不自动恢复数据库；如果新版本执行过不兼容迁移，需要按本节后面的步骤恢复备份。

两个脚本已做 `bash -n` 语法检查和 `rollback.sh --list` 只读验证；首次实际发布建议在旁观察，确认备份、迁移和健康检查输出都正常。

升级：

```bash
# 1. 上传并解压新版本到 /opt/ipms/releases/<新版本>
# 2. 如依赖有变化，重新 pip install
sudo -u ipms /opt/ipms/venv/bin/pip install -r /opt/ipms/releases/<新版本>/backend/requirements.txt

# 3. 先执行一次备份，再执行迁移
systemctl start ipms-backup.service
sudo -u ipms bash -c 'set -a; . /etc/ipms/ipms.env; set +a; \
  cd /opt/ipms/releases/<新版本>/backend && /opt/ipms/venv/bin/alembic upgrade head'

# 4. 切换代码并更新前端静态文件
ln -sfn /opt/ipms/releases/<新版本> /opt/ipms/current
rm -rf /usr/share/nginx/ipms/*
cp -r /opt/ipms/current/frontend/dist/. /usr/share/nginx/ipms/
chown -R root:root /usr/share/nginx/ipms
chmod -R 755 /usr/share/nginx/ipms

# 5. 重启并验证
systemctl restart ipms
nginx -t && systemctl reload nginx
curl -s http://127.0.0.1:8000/health
```

回滚：

```bash
ln -sfn /opt/ipms/releases/<旧版本> /opt/ipms/current
rm -rf /usr/share/nginx/ipms/*
cp -r /opt/ipms/current/frontend/dist/. /usr/share/nginx/ipms/
systemctl restart ipms
systemctl reload nginx
```

若新版本已执行过不兼容迁移，仅切回旧代码不够，必须恢复升级前的数据库备份；不要盲目执行 `alembic downgrade`。

## 11. 已知限制与待确认项

- **已完成一次实际部署（2026-11-16）**：openEuler 22.03 SP4 + PostgreSQL 13.23，迁移、服务、Nginx、浏览器登录、PDF 预览/识别、图片 OCR 已验证；生产环境的材料上传/下载、Excel 导入导出、文件恢复尚未逐项验证。
- **服务器自带 Python 3.9.9 不能直接使用**：必须按第 3.1 节安装 3.10+（推荐 3.12），且不要替换系统 `python3`。项目未在 Python 3.10/3.11 上实测，只在 3.12.10 上通过测试。
- **FastAPI 版本必须 ≥ 本次修复后的版本**：`requirements.txt` 已固定 `fastapi==0.115.14`，8 个 204 路由显式声明 `response_model=None`；若回退到 0.115.6 会启动失败。
- **服务器如无法访问 PyPI**：需要离线 wheel 包，当前发布包不包含 Python 依赖。
- **PDF 文本层依赖 PyMuPDF**：`requirements.txt` 已包含 `pymupdf==2.1`，文字层 PDF 可预览和识别；扫描件 PDF、JPG/PNG 使用 EasyOCR 1.7.2（已安装，CPU 版 torch，`quantize=False`），模型在 `/opt/ipms/.EasyOCR/model`。DOCX 仍不支持识别。
- **NumPy 必须固定 1.26.4**：PyMuPDF 依赖会拉取 NumPy；当前服务器 CPU 不支持 NumPy 2.5 的 X86_V2 baseline，升级会导致 Excel 导入 500。`requirements.txt` 已固定并注释原因。
- **未配置 HTTPS**：仅内网访问；若以后跨网段或公网访问，必须先加 HTTPS、限制来源并重新评估 CORS。
- **单 worker 部署**：见第 6 节说明。
- **SELinux**：如果服务器是 Enforcing，Nginx 反代和静态目录都需要按第 7 节处理；若镜像已关闭 SELinux，可跳过布尔值设置。
- **日志**：后端日志进 `journalctl -u ipms`，Nginx 日志在 `/var/log/nginx/`。
- **对象存储**：目前是本地磁盘；扩容或多实例部署前需要替换存储实现。
- CORS 仍只允许 `http://localhost:5173`，通过 Nginx 同源访问不受影响；不要把前端改成跨域直连 8000。

## 12. 本次实际部署记录（2026-11-16）

| 项 | 实际值 |
|---|---|
| 服务器 | `10.20.0.18`，openEuler 22.03 LTS-SP4，8 核 / 7.2 GB |
| Python | 3.12.10，安装于 `/opt/python3.12`，未替换系统 3.9.9 |
| PostgreSQL | 13.23，数据目录 `/var/lib/pgsql/data`，监听 `127.0.0.1` 和 `10.20.0.18:5432` |
| Nginx | 1.21.5，`server_name 10.20.0.18`，静态目录 `/usr/share/nginx/ipms` |
| SELinux | Disabled |
| 发布版本 | `20261116-180105`，`/opt/ipms/current` 指向该版本 |
| 发布包归档 | `/opt/ipms/packages/ipms-<版本>.tar.gz` |
| 虚拟环境 | `/opt/ipms/venv` |
| 配置 | `/etc/ipms/ipms.env`（root:ipms，640） |
| 上传文件 | `/var/lib/ipms/storage`（ipms:ipms，750） |
| 管理员 | `admin`，初始密码文件 `/root/ipms-admin-password.txt`（600） |
| 防火墙 | `10.20.0.0/24`、`172.20.0.0/22`、`192.168.203.0/24` 可访问 80 和 5432 |
| 自动备份 | `ipms-backup.timer` 每天 02:00，保留 14 天；备份目录 `/var/backups/ipms` |
| 会话策略 | 退出登录只撤销当前会话，其他设备保持登录；默认有效期 720 分钟 |
| SSH 端口转发 | `AllowTcpForwarding local`（供 Navicat SSH 隧道连接数据库；原配置已备份） |
| 数据库直连 | `listen_addresses` 含 `10.20.0.18`；`pg_hba.conf` 对三个内网网段开放 `ipms` 库 SCRAM 登录 |
| OCR | EasyOCR 1.7.2 + CPU torch 2.5.1；模型在 `/opt/ipms/.EasyOCR/model`；`quantize=False` |
| 迁移版本 | `0010_copyright_certificate_date (head)`，19 张业务表 |

本次实际踩到并已修正的问题：

1. openEuler 仓库没有 `python3.10+`；从源码编译 Python 3.12.10，下载源使用华为云镜像。
2. PostgreSQL 13 默认 `ident` + `password_encryption=md5`；改为 `scram-sha-256` 并重设密码。
3. `/etc/ipms` 权限过严，导致 `ipms` 用户读不到环境文件；改为 `root:ipms 750`。
4. FastAPI `0.115.6` 在 204 路由上启动断言失败；依赖改为 `0.115.14`，并在所有 204 路由声明 `response_model=None`。
5. Nginx 自带默认站点与本项目同为 `server_name _`；改为实际 IP，避免请求落到默认站点。
6. 客户端先后出现在 `172.20.0.0/22` 和 `192.168.203.0/24`（Wi-Fi 切换后 DHCP 地址变化），不是服务器所在的 `10.20.0.0/24`；firewalld 三条来源规则都要保留。

验证命令与结果见 `docs/VERIFICATION.md` 第三十四节。
