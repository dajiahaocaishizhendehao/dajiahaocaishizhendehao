# 后端服务（FastAPI）

## 启动

```bash
python -m venv .venv
.venv\Scripts\activate           # Windows
pip install -r requirements.txt

copy .env.example .env
alembic upgrade head
python -m tools.create_admin --username admin --password 'ChangeMe!123'
uvicorn app.main:app --reload --port 8000
```

## 目录

```text
app/
  main.py        应用入口与 CORS
  config.py      环境变量配置
  database.py    引擎、会话与 Base
  models.py      全部 ORM 模型与枚举
  schemas.py     请求 / 响应模型
  security.py    密码哈希、会话令牌、权限判断
  storage.py     本地文件存储
  deps.py        认证依赖与权限依赖
  services.py    审计、分页与校验
  routers/       按模块拆分的接口
alembic/         迁移环境与基线迁移
tests/           pytest 测试
tools/           运维脚本
```

## 约定

- 所有写操作都写 `audit_logs`，且不记录密码、令牌与文件内容。
- 文件二进制不入库，数据库只存 `storage_key`、`sha256`、大小与版本。
- 下载接口校验登录态与档案存在性；已取消部门数据范围，不再按部门返回 404。
- 金额使用 `Numeric(14,2)`，不使用浮点。
- 业务日期用 `Date`，操作时间用带时区 `DateTime`。

## 测试

```bash
pytest -q
```

测试使用内存 SQLite；生产配置仍为 PostgreSQL。

### 没有 pip 环境时怎么跑

若本机存有一份已安装依赖的目录（含 fastapi / sqlalchemy / uvicorn / alembic），可以直接用 `PYTHONPATH` 挂载，无需安装：

```bash
set PYTHONPATH=<本仓库>/backend;<依赖目录>
set DATABASE_URL=sqlite+pysqlite:///<绝对路径>/check.db
python scripts/live_api_check.py     # 真实启动 uvicorn 并跑 32 项 HTTP 检查
cd backend && alembic upgrade head   # 验证迁移可执行
```

仓库根目录的 `scripts/verify.py` 支持这些环境变量：`IPMS_SCHEMA_PYTHON`、`IPMS_LIVE_PYTHON`、`IPMS_DEPS`、`IPMS_NODE`、`IPMS_LIVE=1`。

测试文件：

- `tests/test_domain.py`：纯业务规则单测（零依赖，可直接用 unittest 运行）
- `tests/test_schemas.py`：Pydantic 请求/响应模型校验（需 pydantic，不需要数据库）
- `tests/test_http_contract.py`：HTTP 序列化与错误格式（需 fastapi + httpx，不需要数据库）
- `tests/test_config.py`：配置与环境变量覆盖（需 pydantic-settings）
- `tests/test_storage.py`：本地文件存储真实读写（零依赖）
- `tests/test_request_context.py`：审计来源 IP 解析（需 starlette）
- `tests/test_auth.py`、`tests/test_assets.py`、`tests/test_records.py`、`tests/test_billing_stats.py`、`tests/test_admin.py`：API 集成测试（需完整依赖与数据库会话，当前环境未执行）

业务规则集中在 `app/domain.py`，可脱离 FastAPI 与数据库测试：

```bash
python -m unittest discover -s tests -t . -p "test_domain.py"
```

接口静态审计（仓库根目录执行）：

```bash
python scripts/api_audit.py
```

会检查重复路由、缺少鉴权依赖的接口（登录除外）、未在 `api_router` 注册的路由模块。

## 导入导出

- 导出：`GET /api/export/assets.csv`（写入审计；已取消部门范围，导出全部未删除档案）
- 导入：`POST /api/import/assets`，支持 UTF-8 CSV / XLSX 首工作表，模板列为 `我方文号,申请号,案件名称,专利所有权人,官费应缴纳日,本次官费缴纳至,本次官费缴纳金额,缴纳日期`，只有 `案件名称` 必填；`GET /api/import/assets/template.xlsx` 下载模板
- 导入会创建档案主档、专利子档案，并按填写的列创建专利权人（`parties` + `asset_parties`）和官费记录（`fees`，年费类型）；空白可选列不生成数据
