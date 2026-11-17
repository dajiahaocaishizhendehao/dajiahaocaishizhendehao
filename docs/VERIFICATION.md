# 验证状态说明

本文件如实记录：哪些验证**已经实际执行**，哪些**尚未执行**，以及未执行的原因和补齐方式。

更新时间：2026-11-12

## 一、已执行并通过

| 检查 | 命令 | 结果 |
|---|---|---|
| Python 语法编译（3.12） | `python scripts/verify.py --offline` | 全部文件通过 |
| Python 语法编译（3.11） | 用 3.11 解释器执行 `compileall` | 通过（跨版本验证） |
| 项目内导入解析 | 同上 | 309 处，0 错误 |
| 前端结构与导入 | 同上 | 20 个文件（16 个 Vue），0 错误 |
| 前端路由目标 | 同上 | 所有 `RouterLink` 目标已注册 |
| ORM 模型检查 | 同上 | 24 个模型 / 22 张表 / 146 处属性访问 |
| 接口静态审计 | 同上 | 50 个接口，无重复路由、均有鉴权 |
| 前后端契约 | 同上 | 6 个 DTO 字段对齐 |
| 纯业务规则单测 | 同上 | 41 个测试通过 |
| 查询条件与数据范围单测 | 同上 | 14 个测试通过 |
| Pydantic 模型契约测试 | 同上（需 pydantic 解释器） | 22 个测试通过 |
| HTTP 层契约测试 | 同上（需 fastapi + httpx） | 8 个测试通过 |
| 配置模块测试 | 同上（需 pydantic-settings） | 5 个测试通过 |
| 本地存储测试 | 同上（真实临时目录读写） | 5 个测试通过 |
| 请求上下文测试 | 同上（需 starlette） | 6 个测试通过 |
| Vue 单文件组件编译 | `node frontend/.sfc/check.mjs` | 16 个组件全部编译通过（模板 16 / 脚本 16） |
| 前端 TypeScript 检查 | 用本机 tsc 检查 `src/env.d.ts` + `src/main.ts` | strict 模式通过（含 router / api / 全部页面导入） |
| **前端生产构建** | `vite build` | 成功产物：`dist/index.html` 0.40 kB、CSS 6.73 kB、JS 173.73 kB（gzip 58.02 kB） |
| **浏览器渲染验证** | 无头 Edge 加载 `dist` 并导出 DOM | `#app` 已挂载，登录页渲染完成，路由守卫把未登录用户跳到 `#/login` |
| **登录后页面渲染** | `python scripts/browser_check.py` | 13 项检查通过：看板 / 证书 / 日期三个页面渲染出真实接口数据，匿名访问被挡回登录页 |
| **浏览器交互** | `python scripts/cdp_login_check.py` | 10 项检查通过：真实填写表单、点击登录、跳转工作台、刷新后保持登录态 |
| **端到端服务验证** | `python scripts/live_api_check.py` | **真实启动 uvicorn，35 项 HTTP 检查全部通过** |
| **Alembic 迁移** | `alembic upgrade head`（SQLite） | 成功建立 22 张业务表，版本标记 `0001_initial` |
| **PostgreSQL 方言编译** | `python scripts/pg_compat_check.py` | 22 张表 DDL 与 5 类代表性查询均可编译；`NUMERIC(14,2)`、`ILIKE`、`NULLS LAST`、`LIMIT/OFFSET` 均符合预期 |
| **PostgreSQL DDL 生成** | `python scripts/pg_ddl_check.py` | Alembic 离线模式在 PG 方言下生成 554 行 DDL，14 项结构断言通过 |
| 安全模块自检 | `python scripts/smoke_security.py` | 17 项断言通过 |

反向验证（确认检查器不是空跑）：

- 在 `backend/app/` 注入 `IpAsset.this_field_does_not_exist`，模型检查器立即报错并返回非零退出码；删除后恢复通过。

### 通过真实运行发现并修复的缺陷

1. **借出日期校验从未生效**：`LoanIn` 的 `due_date` / `return_date` 校验器误用 `info.data` 读取尚未写入的字段，导致「归还日期早于借出日期」不会被拒绝。由新增的 Pydantic 测试发现，已改为按字段分别校验并复测通过。
2. **受限角色未分配部门时会被放大为全量访问**（安全缺陷）：`data_scope_department` 对 `dept_user` / `viewer` 返回 `user.department_id`，当其为空时返回 `None`，而 `None` 在调用方表示「不限制」。修复方式：受限角色无部门时返回空串哨兵，`scoped_assets` 追加 `false()` 条件、`ensure_asset_visible` 一律 404、导出与统计同样收紧。
3. **导入去重逻辑埋在路由里**：文件内编号去重与逐行校验原先写在 `import_assets` 路由中，无法脱离数据库测试。已抽为 `domain.parse_import_rows()`，并补 4 个测试。
4. **审计取 IP 逻辑依赖数据库**：`deps.client_ip` 因模块导入链依赖 SQLAlchemy 而无法单测。已迁到 `app/request_context.py`，`deps` 保留兼容入口。

### 关于运行环境

本机 PyPI / npm 均不可达，但发现一个已装 FastAPI 0.136.1、Pydantic 2.13.3、httpx 0.28.1 的 Python 3.11 环境（无 SQLAlchemy、无 pytest）。

为此做了两处结构调整，使契约层可以真实运行：

- 枚举从 `app/models.py` 迁到 `app/constants.py`，`app/schemas.py` 只依赖 constants；
- 校验规则集中到 `app/domain.py`。

指定该解释器即可复现上表中的 Pydantic 与 HTTP 测试：

```bash
IPMS_SCHEMA_PYTHON=<装有 pydantic 的 python> python scripts/verify.py --offline
```

### 前端编译检查是怎么做到的

npm 不可用，但本机磁盘上存在其他项目的 `node_modules`，其中包含 `@vue/compiler-sfc` 3.5.39、`vue` 3.5.39 与 `typescript` 6.0.3。

于是把这些包（含它们的依赖）复制到 `frontend/.sfc/node_modules`，用一个小脚本直接调用 Vue 官方编译器：

```bash
node frontend/.sfc/check.mjs      # 解析 + 编译全部 .vue
```

它做的是真实编译，不是正则检查：`parse()` 解析 SFC，`compileScript()` 处理 `<script setup>`，`compileTemplate()` 生成渲染函数，`compileStyle()` 处理样式块。当前 16 个组件全部通过。

`src/api.ts` 没有任何外部导入，因此可以用 tsc 单独做 strict 类型检查，也已通过。

注意：

- `frontend/.sfc/` 是从本机已有依赖复制出来的沙箱，已加入 `.gitignore`，不属于仓库内容；
- 换一台机器没有这些包时，`scripts/verify.py` 会跳过该步骤并给出提示，不会假装通过。

## 二、端到端验证做了什么

`scripts/live_api_check.py` 会：

1. 在工作区建临时 SQLite 库并写入演示部门与三种角色账号；
2. 以子进程启动真实 `uvicorn`；
3. 用标准库 `urllib` 发真实 HTTP 请求；
4. 结束后关闭服务、删除临时库。

覆盖的 35 项检查包括：

- 未登录 401、错误密码 401、登录成功
- 创建专利档案 201、重复编号 409、跨类型字段 422
- 管理员跨部门可见 2 条、关键词搜索命中 1 条、详情返回专业字段
- 状态更新、证书登记、日期事项创建与完成
- 费用部分支付状态推导（`partial`）、发票关联费用
- 材料上传与下载内容一致
- 统计看板（total=2、granted_rate=50.0）、统计口径字段、年度统计声明 `created_at`
- CSV 导出含案件名称、Excel 导出为合法 xlsx（表头与行数校验）、CSV 导入创建 1 条跳过 1 条
- 只读账号写入 403、只读账号只看到本部门 1 条
- **受限且无部门的账号看不到任何数据（total=0）** —— 验证了本轮的越权修复
- 审计日志已记录、逻辑删除 204、删除后详情 404

> 说明：本次端到端验证使用 SQLite。PostgreSQL 未安装，因此 PostgreSQL 方言下的行为（如 `NULLS LAST`、时区类型）仍未验证。

## 二·五、PostgreSQL 兼容性到了哪一步

本机没有任何 PostgreSQL 服务：全盘搜索不到 `postgres.exe` / `pg_ctl.exe`，Docker 守护进程未运行，WSL 访问被拒（`WSL_E_ACCESSDENIED`）。

因此改成**方言级验证**：用 SQLAlchemy 的 PostgreSQL 方言把模型 DDL 与代表性查询编译成 SQL 文本。

```bash
python scripts/pg_compat_check.py
```

结果（12 项检查全部通过）：

- 22 张表全部可生成 PostgreSQL DDL；
- 金额列为 `NUMERIC(14, 2)`，币种 `VARCHAR(3)`，JSON 列为 `JSON`，时间列为 `TIMESTAMP WITH TIME ZONE`，业务日期为 `DATE`；
- 枚举使用 `CHECK` 约束而非原生 ENUM，便于后续调整取值；
- 全部索引可编译；
- 5 类代表性查询可编译，`NULLS LAST`、`ILIKE`、`LIMIT/OFFSET` 均正确出现在生成的 SQL 中。

**这只能说明「能编译为 PG SQL」，不能替代连接真实服务器执行。** 真正未验证的是：连接、事务、时区往返、`psycopg` 驱动行为。

### 更接近真实迁移的一步：Alembic 离线 DDL

`scripts/pg_ddl_check.py` 使用 `alembic upgrade head --sql` 的离线模式，让 Alembic 以 PostgreSQL 方言渲染出**实际会执行的建表语句**（走的是 alembic env + 迁移脚本，而不是直接编译 metadata），产物写入 `backend/var/schema-postgres.sql`。

14 项断言通过：

- 业务表 22 张，另含 `alembic_version`；
- 金额 `NUMERIC(14, 2)`、币种 `VARCHAR(3)`、JSON 列、`TIMESTAMP WITH TIME ZONE`、`DATE`；
- 主键、外键（≥15 个）、索引、`CHECK` 约束齐全；
- 关键唯一约束存在：`uq_ip_assets_asset_no`（该约束已在 D-018 中随字段删除）、`uq_invoice_fee`；
- 不含 SQLite 专有语法（如 `AUTOINCREMENT`）。

仍未验证的仍是「连上服务器真正执行这 554 行 SQL」。

顺带修复的问题：`app/database.py` 原先在模块导入时就 `create_engine`，导致任何只想要 `Base.metadata` 的工具都被迫安装数据库驱动。已改为 `get_engine()` 懒加载，`SessionLocal` 在 `get_db()` 中绑定。

## 三、前端构建与浏览器验证
npm 不可用，但本机 pnpm store 与另一个项目里存在完整的前端工具链（vite 6.4.3、@vitejs/plugin-vue 5.2.4、rollup 4.62.2、esbuild 0.21.5、@vue/compiler-sfc 3.5.39、vue-router 4.2.5）。把它们复制到 `frontend/node_modules` 后：

```bash
cd frontend
node node_modules/vite/bin/vite.js build
```

结果：

```
vite v6.4.3 building for production...
✓ 57 modules transformed.
dist/index.html                   0.40 kB │ gzip:  0.31 kB
dist/assets/index-BuGH_qBo.css    6.73 kB │ gzip:  2.10 kB
dist/assets/index-BnYuu-w1.js   173.73 kB │ gzip: 58.02 kB
✓ built in 1.04s
```

随后用 `python -m http.server` 托管 `dist`，再用无头 Edge 打开并导出 DOM，确认：

- `#app` 上有 `data-v-app` 属性（Vue 已挂载）；
- 渲染出登录卡片（`.login-card`、账号输入框、密码输入框、登录按钮）；
- 页面标题变成「登录 · 知产云档」，说明路由守卫把未登录访问重定向到了 `#/login`。

注意事项：

- 该构建需要 esbuild 以管道方式启动子进程，在当前沙箱的受限模式下会报 `spawn EPERM`，必须在完整权限下执行；
- `frontend/node_modules` 与 `dist` 均已在 `.gitignore` 中排除，不属于仓库内容。

## 四、登录后的浏览器验证

`scripts/browser_check.py` 把「后端 + 前端产物 + 浏览器」串起来：

1. 子进程启动 uvicorn（SQLite 临时库，写入管理员账号）;
2. 进程内起静态服务器托管 `frontend/dist`，并把 `/api/*` 反向代理到后端；
3. 通过 HTTP 登录拿到令牌；
4. 生成一个测试页，在应用脚本执行前把令牌写入 `localStorage`；
5. 无头 Edge 依次打开 `#/`、`#/materials`、`#/dates` 并导出 DOM；
6. 断言每个页面渲染出预期内容，并验证匿名访问会被路由守卫挡回登录页。

结果（13 项全部通过）：

- 看板渲染出「知识产权工作台」「知识产权总数」「即将到期」；
- 证书页渲染出「已取得权利与证书」「电子证书」；
- 日期页渲染出「日期台账」「不构成法律建议」；
- 匿名访问时出现登录卡片。

这说明前端不是「能编译」，而是**能带着真实令牌调用真实接口并渲染页面**。

限制：该步骤需要浏览器进程，必须在完整权限下运行；`_e2e.html` 是运行时生成的临时文件，执行后自动删除。

## 四·五、浏览器交互验证（登录流程）

`scripts/cdp_login_check.py` 用标准库实现了一个最小 WebSocket 客户端，直接驱动 Edge 的 Chrome DevTools Protocol，不需要 Playwright：

1. 启动 uvicorn（SQLite）、静态服务器与带 `--remote-debugging-port` 的无头 Edge；
2. `Page.navigate` 打开登录页；
3. `Runtime.evaluate` 向 `#username` / `#password` 写入值并派发 `input`、`change` 事件（触发 Vue 的 v-model）；
4. 点击登录按钮；
5. 轮询 `location.hash` 与 `document.body.innerText`；
6. 刷新页面确认会话保持。

结果（10 项全部通过）：

- 登录页渲染、初始地址为 `#/login`；
- 账号密码成功填入表单、点击登录按钮生效；
- 跳转到 `#/`，工作台渲染出「知识产权工作台」与统计卡片；
- 登录表单被替换；
- `Page.reload` 后仍处于登录态。

过程中遇到并解决的问题：Edge 首次启动会打开同步引导页覆盖目标地址，改为「先用 CDP 连接 about:blank，再 `Page.navigate`」，并加上 `--no-first-run --disable-sync` 等参数。

## 五、尚未执行

| 项目 | 原因 |
|---|---|
| 连接 PostgreSQL 运行 | 本机无 PostgreSQL 服务，也无 Docker 守护进程 |
| `pytest` | 全机未安装 pytest；当前所有测试均以 `unittest` 运行 |
| `pnpm install` / `vite build` | 无法访问 npm registry；前端依赖是从本机其他项目复制的 |
| 浏览器内实际点击联调 | 缺少完整前端依赖（vite 运行时），仅完成编译与类型检查 |

因此，以下内容**没有得到运行验证**，可能存在只有运行才能暴露的问题：

- SQLAlchemy 映射与 Alembic 建表是否成功；
- FastAPI 依赖注入、Pydantic 序列化、文件上传下载；
- Vue 编译与页面实际交互。

## 三、在可用环境里如何补齐

前提：可访问 PyPI 与 npm，或已有离线包；本机可运行 PostgreSQL 14+。

```bash
# 1. 数据库
psql -c "CREATE USER ipms WITH PASSWORD 'ipms';"
psql -c "CREATE DATABASE ipms OWNER ipms;"

# 2. 后端
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
alembic upgrade head
python -m tools.create_admin --username admin --password 'ChangeMe!123'
pytest -q
uvicorn app.main:app --reload --port 8000

# 3. 前端（另开终端）
cd frontend
pnpm install
pnpm dev
```

验收要点：

1. `alembic upgrade head` 后能看到 22 张表；
2. `pytest -q` 全绿（当前 5 个 API 测试文件 + 1 个纯规则测试文件）；
3. `http://127.0.0.1:8000/docs` 能打开且接口数量为 49；
4. 前端能登录、新建档案、上传材料、登记证书；
5. 越权场景：用 `viewer` 账号调用写接口应返回 403。

## 四、怎么复现（本机环境）

环境变量说明：

| 变量 | 作用 |
|---|---|
| `IPMS_SCHEMA_PYTHON` | 装了 pydantic / fastapi 的解释器，用于契约层测试 |
| `IPMS_LIVE_PYTHON` | 装了 sqlalchemy / uvicorn 的解释器，用于端到端验证 |
| `IPMS_DEPS` | 依赖目录（`PYTHONPATH` 追加），无需 pip 安装 |
| `IPMS_NODE` | node 可执行文件路径 |
| `IPMS_LIVE=1` | 启用手动步骤：真实启动服务 |

```bash
python scripts/verify.py --offline \
  # 例如：
  IPMS_SCHEMA_PYTHON=<py> IPMS_LIVE_PYTHON=<py> IPMS_DEPS=<deps> IPMS_NODE=<node> IPMS_LIVE=1
```

单独复现端到端验证：

```bash
set PYTHONPATH=<backend>;<deps>
python scripts/live_api_check.py
```

单独复现迁移：

```bash
set DATABASE_URL=sqlite+pysqlite:///<abs path>/check.db
cd backend && alembic upgrade head
```

## 五、如果暂时无法搭建环境

可以只做离线检查，确认代码结构与规则一致性：

```bash
python scripts/verify.py --offline
python scripts/smoke_security.py
```

这两条命令不依赖任何第三方包，当前环境下已全部通过。

## 六、2026-11-11 基础资料优化验证记录

本次变更：基础资料增加权利人 / 代理机构 / 项目的新建、编辑、逻辑删除；人员页签合并到系统用户；部门页签移除但保留部门数据范围。

已实际执行：

| 检查 | 命令 | 结果 |
|---|---|---|
| 后端完整测试 | `backend/.venv/Scripts/python.exe -m pytest -q` | **169 passed** |
| 新增基础资料测试 | `pytest tests/test_meta.py -q` | 7 passed |
| Vue SFC 编译 | `node frontend/.sfc/check.mjs` | 15 个组件全部通过 |
| 前端生产构建 | `node node_modules/vite/bin/vite.js build` | 66 modules，构建成功 |
| 离线自检 | `python scripts/verify.py --offline` | 离线校验全部通过 |
| ORM 模型检查 | `python scripts/model_check.py` | 22 个模型 / 20 张表 / 235 处属性访问通过 |
| 接口静态审计 | `python scripts/api_audit.py` | 64 个接口，无重复路由、均有鉴权 |
| 前后端契约 | `python scripts/contract_check.py` | 通过 |

未执行：

- **真实服务 + 浏览器端到端验证**：当前可用 Python 环境均未安装 `uvicorn`（`No module named uvicorn`），无法启动后端；未擅自安装依赖。因此 `/meta` 页面与真实 API 的联调结果标记为**未验证**。
- **PostgreSQL DDL 校验**：该环境未安装 Alembic，`verify.py` 已明确提示跳过，而不是记为通过。
- **`vue-tsc` 全量类型检查**：本机未安装 `vue-tsc`；已用 SFC 真实编译与 Vite 构建替代。

本次同时修复了两处自检脚本误报：

1. `scripts/model_check.py` 与 `scripts/verify.py` 的导入扫描会遍历 `backend/.venv`，把第三方包自带测试当成业务代码；已排除虚拟环境与缓存目录。
2. 费用审计摘要改为固定两位小数（`1.00 CNY`），消除 SQLite 与 PostgreSQL 对 `Numeric` 标度处理不一致导致的测试随机失败。

## 七、2026-11-11 取消部门字段验证记录

本次变更：按 D-014 彻底取消部门——删除 `departments` 表和 `users` / `ip_assets` / `projects` / `persons` 的 `department_id`，删除后端部门数据范围过滤，前端系统管理与基础资料不再出现部门；新增迁移 `0007_drop_departments`。

已实际执行（在部门字段删除**之后**重新运行）：

| 检查 | 命令 | 结果 |
|---|---|---|
| 后端完整测试 | `backend/.venv/Scripts/python.exe -m pytest -q` | **164 passed** |
| 接口静态审计 | `python scripts/api_audit.py` | 61 个接口（原 64，删除 3 个部门接口），无重复路由、均有鉴权 |
| ORM 模型检查 | `python scripts/model_check.py` | 21 个模型 / 19 张表 / 220 处属性访问通过 |
| Vue SFC 编译 | `node frontend/.sfc/check.mjs` | 15 个组件全部通过 |
| 前端生产构建 | `node node_modules/vite/bin/vite.js build` | 构建成功 |
| 离线自检 | `python scripts/verify.py --offline` | 离线校验全部通过 |
| 前后端契约 | `python scripts/contract_check.py` | 通过（前端不再引用 `department_id`） |
| 源码残留扫描 | `grep -rn "department" backend/app frontend/src backend/tests scripts` | 仅命中 `__pycache__` 二进制缓存，源码无残留 |

未执行：

- **迁移 `0007_drop_departments` 的真实执行与降级**：当前环境未安装 Alembic（`ModuleNotFoundError: No module named 'alembic'`），**未验证**。迁移代码采用 `batch_alter_table` 并按表/列存在性判断，SQLite 与 PostgreSQL 均走同一路径；上线前须在真实库执行 `alembic upgrade head` 与 `alembic downgrade 0006_integrity_ocr` 各一次。
- **真实服务 + 浏览器端到端验证**：环境无 `uvicorn`，`/users` 与 `/meta` 页面与真实 API 的联调**未验证**。
- **`backend/var/schema-postgres.sql`**：该文件是 `scripts/pg_ddl_check.py` 于 2026-11-09 生成的旧产物，仍包含 `departments`，因 Alembic 不可用无法重新生成。它只是校验产物，不是迁移来源，以 `backend/alembic/versions/` 为准。

权限口径变化说明：原先受部门限制的账号现在能看到全部档案，因此新增 `tests/test_resource_access.py` 覆盖「只读账号可见全部档案与关联资源、但写操作仍返回 403」。

## 八、2026-11-11 角色精简验证记录

本次变更：按 D-015 把角色从 `admin` / `ip_admin` / `dept_user` / `viewer` 精简为 `admin`（系统管理员）/ `ip_admin`（管理员）/ `user`（普通用户）；原两个只读角色合并为 `user`；新增迁移 `0008_merge_user_roles`。

已实际执行：

| 检查 | 命令 | 结果 |
|---|---|---|
| 后端完整测试 | `backend/.venv/Scripts/python.exe -m pytest -q` | **164 passed** |
| 安全模块自检 | `python scripts/smoke_security.py` | 通过（普通用户不可写、系统管理员独有用户管理） |
| Vue SFC 编译 | `node frontend/.sfc/check.mjs` | 15 个组件全部通过 |
| 前端生产构建 | `node node_modules/vite/bin/vite.js build` | 成功（JS 223.35 kB / gzip 73.95 kB） |
| 前后端契约 | `python scripts/contract_check.py` | 通过 |
| 离线自检 | `python scripts/verify.py --offline` | 离线校验全部通过 |
| ORM 模型检查 | `python scripts/model_check.py` | 通过 |
| 旧角色残留扫描 | `grep -rn "dept_user\|viewer\|部门用户\|普通查看用户"` | 源码与前端无残留，仅历史决策记录保留说明 |

未执行：

- **迁移 `0008_merge_user_roles` 的真实执行与降级**：环境无 Alembic，**未验证**。迁移只执行 `UPDATE users SET role='user' WHERE role IN ('dept_user','viewer')`；角色列以 VARCHAR 存储（`native_enum=False`），不涉及类型变更。上线前须在真实库执行 `alembic upgrade head` 并核对原只读账号角色已变为 `user`。
- **端到端与浏览器验证**：环境无 `uvicorn`，`live_api_check.py` 已把演示只读账号改为 `normal` / `user` 但未运行，**未验证**。

## 九、2026-11-11 人员移入系统管理验证记录

本次变更：按 D-016 删除基础资料的“人员”页签；用户的搜索、新建、编辑（含姓名、角色、手机、邮箱、状态、重置密码）、删除全部在“系统管理 → 用户”提供。后端 `/api/users` 的 `q`、`PATCH`、`DELETE` 原本已存在，本次只新增测试覆盖。

已实际执行：

| 检查 | 命令 | 结果 |
|---|---|---|
| 后端完整测试 | `backend/.venv/Scripts/python.exe -m pytest -q` | **165 passed**（新增用户搜索与联系方式编辑测试） |
| Vue SFC 编译 | `node frontend/.sfc/check.mjs` | 15 个组件全部通过 |
| 前端生产构建 | `node node_modules/vite/bin/vite.js build` | 成功（CSS 26.97 kB / JS 223.48 kB） |
| 前后端契约 | `python scripts/contract_check.py` | 通过（`User` 已对齐 `UserOut` 的 email / phone / is_active） |
| 离线自检 | `python scripts/verify.py --offline` | 离线校验全部通过 |
| 旧入口残留扫描 | `grep -n "人员\|api.users" frontend/src/views/MetaView.vue` | 仅剩说明文案，无人员页签、无用户增删改代码 |

未执行：

- **真实服务 + 浏览器联调**：环境无 `uvicorn`，系统管理页的搜索、编辑、删除抽屉与真实接口的联调**未验证**；仅完成 SFC 编译与生产构建。
- **删除当前登录账号的界面表现**：前端禁用按钮、服务端返回 422，已有服务端测试覆盖；浏览器实际点击效果**未验证**。

## 十、2026-11-11 费用台账分页条数验证记录

本次变更：费用台账分页栏显示“共 N 条 · 每页 X 条”，并允许在 20 / 50 / 100 之间切换；默认 20 条，切换后回到第 1 页重新加载。

已实际执行：

| 检查 | 命令 | 结果 |
|---|---|---|
| Vue SFC 编译 | `node frontend/.sfc/check.mjs` | 15 个组件全部通过 |
| 前端生产构建 | `node node_modules/vite/bin/vite.js build` | 成功（JS 223.92 kB / gzip 74.25 kB） |

未执行：

- **浏览器交互验证**：环境无 `uvicorn`，切换每页条数后的实际请求与渲染**未验证**。接口 `GET /api/fees` 的 `page_size` 允许 1–200，20/50/100 均在范围内。

## 十一、2026-11-11 新建档案取消内部编号验证记录

本次变更：按 D-017 删除“全部知识产权 → 新建档案”的内部编号输入，案件名称移至表单首位；商标 / Logo 页“新建商标”同步删除内部编号，商标名称移至首位；后端未提供 `asset_no` 时生成 `AUTO-YYYYMMDD-XXXXXXXX` 系统编号。

已实际执行：

| 检查 | 命令 | 结果 |
|---|---|---|
| 后端完整测试 | `backend/.venv/Scripts/python.exe -m pytest -q` | **167 passed**（新增 2 项：编号可省略、无编号创建生成唯一编号） |
| Vue SFC 编译 | `node frontend/.sfc/check.mjs` | 15 个组件全部通过 |
| 前端生产构建 | `node node_modules/vite/bin/vite.js build` | 成功（JS 223.52 kB / gzip 74.16 kB） |
| 前后端契约 | `python scripts/contract_check.py` | 通过 |
| 离线自检 | `python scripts/verify.py --offline` | 离线校验全部通过 |

未执行：

- **浏览器交互验证**：环境无 `uvicorn`，新建抽屉的实际提交与自动编号回显**未验证**。
- **商标 / Logo 页新建表单**：已同步删除内部编号字段，SFC 编译与构建通过；浏览器实际提交**未验证**。

## 十二、2026-11-11 彻底删除内部编号验证记录

本次变更：按 D-018 彻底删除内部编号。删除 `ip_assets.asset_no` 列与 `uq_ip_assets_asset_no_active` 唯一索引；删除 `AssetCreate` / `AssetListItem` / `FeeOut` 中的 `asset_no`；新建、详情、列表、商标卡片、工作台、日期 / 费用 / 发票选择器不再展示该字段；CSV / XLSX 导出去掉“档案编号”列；导入不再解析旧模板 `asset_no` 列；搜索只按案件名称与我方文号；新增迁移 `0009_drop_asset_no`。

已实际执行：

| 检查 | 命令 | 结果 |
|---|---|---|
| 后端完整测试 | `backend\.venv\Scripts\python.exe -m pytest -q` | **165 passed**（删除重复编号、生成编号等 4 项旧测试，新增 2 项“旧字段被忽略”测试） |
| 离线自检 | `python scripts/verify.py --offline` | 全部通过（SFC 15 个组件、TypeScript strict、契约层测试） |
| ORM 模型检查 | `python scripts/model_check.py` | 21 个模型 / 19 张表 / 217 处属性访问通过 |
| 接口静态审计 | `python scripts/api_audit.py` | 61 个接口，无重复路由、均有鉴权 |
| 前后端契约 | `python scripts/contract_check.py` | 通过（前端不再引用 `asset_no`） |
| 安全模块自检 | `python scripts/smoke_security.py` | 全部通过 |
| PostgreSQL DDL | `python scripts/pg_ddl_check.py` | 19 张业务表；断言“内部编号列与唯一索引已彻底移除”通过 |
| 前端生产构建 | `node node_modules/vite/bin/vite.js build` | 68 modules，JS 222.97 kB / gzip 73.93 kB，CSS 27.12 kB |
| 端到端服务验证 | 真实启动 uvicorn + 临时 SQLite | **32 项 HTTP 检查全部通过**，含“创建响应不再返回内部编号”、导出表头 `['名称','类型']` |
| 迁移 0009 升级（模拟历史库） | `alembic upgrade head` | 成功删除 `asset_no` 列与唯一索引，版本变为 `0009_drop_asset_no` |
| 迁移 0009 降级 | `alembic downgrade 0008_merge_user_roles` | 成功重建可空 `asset_no` 列与部分唯一索引（历史取值不可恢复） |
| 全新库完整迁移链 | `alembic upgrade head`（空库） | 0001 → 0009 全部成功，19 张表，无 `asset_no` |

为避免全新库失败，`0006_integrity_ocr` 增加列存在性判断：0001 以当前 metadata 建基线后，新建库已没有 `asset_no`，该迁移不再尝试为不存在的列建索引。

未执行：

- **真实 PostgreSQL 上的迁移**：本机无 PostgreSQL 服务，只验证了 SQLite 上的升级/降级与 PG 方言离线 DDL。
- **浏览器点击验证**：未运行无头浏览器实际操作；内部编号的移除已由 SFC 编译、生产构建、接口响应与端到端检查覆盖。
- **删除前的历史编号备份**：按用户确认“彻底删除”，已有编号未导出、不可恢复。

## 十三、界面枚举字段中文化验证记录（2026-11-11 变更，2026-11-12 验证）

本次变更：将界面中仍显示为英文枚举值的字段统一改为中文。

| 位置 | 字段 | 原显示 | 现显示 |
|---|---|---|---|
| 工作台 → 待处理事项 | `date_type` | `planned` / `due` / `actual` / `custom` | 计划日期 / 截止日期 / 实际完成日期 / 自定义 |
| 档案详情 → 人员 | `person_type` | `inventor` / `designer` / `developer` / `contact` | 发明人 / 设计人 / 开发人员 / 联系人 |
| 系统管理 → 操作日志 | `action` | `create` / `update` 等 | 新增 / 修改 / 删除 / 导出 / 导入 / 登录 等 |
| 系统管理 → 操作日志 | `object_type` | `ip_asset` / `user` 等 | 知识产权档案 / 用户 / 费用 / 发票 等 |
| 日期台账 → 状态 | `status` | `canceled` 曾显示为“未完成” | 未完成 / 已完成 / 已取消 |

同时移除档案详情“基本信息”中重复出现的两行“我方文号”。

已实际执行：

| 检查 | 命令 | 结果 |
|---|---|---|
| 后端完整测试 | `backend\.venv\Scripts\python.exe -m pytest -q` | **165 passed** |
| 离线自检 | `python scripts/verify.py --offline` | 全部通过（SFC 15、TypeScript strict、契约层测试） |
| 端到端服务验证 | `python scripts/live_api_check.py` | 真实 uvicorn + SQLite，**32 项 HTTP 检查全部通过** |
| ORM 模型检查 | `python scripts/model_check.py` | 21 个模型 / 19 张表 / 217 处属性访问通过 |
| 接口静态审计 | `python scripts/api_audit.py` | 61 个接口，无重复路由、均有鉴权 |
| 前后端契约 | `python scripts/contract_check.py` | 通过 |
| 安全模块自检 | `python scripts/smoke_security.py` | 15 项断言通过 |
| PostgreSQL DDL | `python scripts/pg_ddl_check.py` | 532 行 PG DDL，14 项断言通过 |
| Vue SFC 编译 | `node frontend/.sfc/check.mjs` | 15 个组件全部通过（模板 15 / 脚本 15） |
| 前端生产构建 | `node node_modules/vite/bin/vite.js build` | 68 modules，JS 223.80 kB / gzip 74.32 kB，CSS 27.12 kB |
| 运行中前端加载新产物 | `curl http://127.0.0.1:5173/` | `index.html` 引用新的 `index-Dr-ymcZx.js` |
| 新中文字符串进入产物 | `grep` 构建产物 | “计划日期”“材料识别”“开发人员”“已取消”均存在 |
| **浏览器渲染（Chrome 无头）** | 临时 SQLite + uvicorn + 静态代理，写入令牌后 `chrome --dump-dom` | 工作台 / 日期 / 档案列表 / 材料 / 基础资料 / 商标 / 系统管理均挂载成功 |
| 工作台中文枚举 | 同上，种子数据含 `planned`、`due` 日期事项 | 页面显示“计划日期”“截止日期”，无 `>planned<` / `>due<` |
| 档案人员中文枚举 | 通过 API 创建 `inventor` 人员并关联档案 | 详情显示“发明人”，无 `>inventor<` |
| 操作日志中文枚举 | 注入脚本点击“操作日志”页签后导出 DOM | 显示“登录 / 用户 / 登录成功”，无 `>login<` / `>user<` |
| 日期状态中文枚举 | 直接置一条日期事项为 `canceled` 后渲染 | 显示“已取消”，无 `>canceled<` |

本次浏览器验证使用 Chrome（Edge 在当前环境中以子进程启动时返回空 DOM、CDP 连接超时，故 `scripts/browser_check.py` 与 `scripts/cdp_login_check.py` 在该环境无法完成；同一产物在 Chrome 中可正常挂载与渲染，判定为环境限制而非页面缺陷）。

未执行：

- **自由文本字段**：项目 / 产品的 `status` 与代理机构的 `service_type` 由用户自由录入，不是枚举值，仍按用户输入原样显示。

说明：映射采用 `标签表[值] ?? 原始值` 形式，后端新增未知枚举值时界面不会空白，而是回退显示原始值。

## 十四、全部知识产权「授权公告日」验证记录（2026-11-12）

本次变更：

- 全部知识产权列表新增「授权公告日」列。数据来源为专利已有的 `patents.grant_date`，软著与商标显示 `—`；**未新增数据库字段，也不需要迁移**。
- 默认排序改为：未取得权利的档案排在最前；已取得的按授权公告日倒序；已取得但无授权公告日的排在其后；组内按更新时间倒序。
- 专利新建 / 编辑抽屉增加「授权公告日」日期输入，写入 `patents.grant_date`；详情页标签由「授权日期」改为「授权公告日」。

实现要点：

- `IpAsset.grant_date` 作为只读属性返回专利授权公告日，列表查询 `outerjoin(Patent)` 后用 `case` 完成排序；`selectinload(IpAsset.patent)` 避免逐行查询。
- 新增测试覆盖：列表返回专利授权公告日、其他类型为 `null`；四种状态组合的默认顺序；通过 `PATCH /api/assets/{id}` 修改授权公告日。

已实际执行：

| 检查 | 命令 | 结果 |
|---|---|---|
| 后端完整测试 | `backend\.venv\Scripts\python.exe -m pytest -q` | **168 passed**（新增 4 项：列表字段、默认排序、可编辑、无日期回退顺序） |
| 档案模块测试 | `pytest tests/test_assets.py -q` | 11 passed |
| 前后端契约 | `python scripts/contract_check.py` | 通过（`AssetDetail` 前后端均 16 字段，含 `grant_date`） |
| 离线自检 | `python scripts/verify.py --offline` | 全部通过（SFC 15、TypeScript strict、契约层测试） |
| ORM 模型检查 | `python scripts/model_check.py` | 21 个模型 / 19 张表 / 224 处属性访问通过 |
| 接口静态审计 | `python scripts/api_audit.py` | 通过，无重复路由、均有鉴权 |
| 端到端服务验证 | `python scripts/live_api_check.py` | 真实 uvicorn + SQLite，**32 项 HTTP 检查全部通过** |
| PostgreSQL DDL | `python scripts/pg_ddl_check.py` | 通过（本次无结构变更，仍 14 项断言） |
| Vue SFC 编译 | `node frontend/.sfc/check.mjs` | 15 个组件全部通过（模板 15 / 脚本 15） |
| 前端生产构建 | `node node_modules/vite/bin/vite.js build` | 68 modules，JS 224.24 kB / gzip 74.40 kB，CSS 27.12 kB |
| 构建产物含新字段 | `grep "授权公告日" dist/assets/*.js` | 命中 4 处；`grant_date` 命中 18 处 |
| **浏览器渲染（Chrome 无头）** | 临时 SQLite + uvicorn + 静态代理，写入令牌后 `chrome --headless=new --dump-dom` | 表头出现「授权公告日」；行顺序为「办理中演示专利 → 较新取得演示专利（2025-09-01）→ 较早取得演示专利（2024-05-01）→ 取得无日期演示软著」；无日期的行显示 `—` |

浏览器渲染的实际单元格内容：

```text
—  专利        —          2026-11-12   （办理中）
—  专利        2025-09-01 2026-11-12   （已取得）
—  专利        2024-05-01 2026-11-12   （已取得）
—  软件著作权  —          2026-11-12   （已取得但无授权公告日）
```

未执行：

- **浏览器内点击「编辑」抽屉并提交新日期**：已通过 `PATCH /api/assets/{id}` 的服务端测试与 SFC/构建验证覆盖，但未在浏览器里真实点击保存。
- **真实 PostgreSQL**：本机无 PostgreSQL 服务，未连接。

## 十五、材料识别「写入档案」防重复点击验证记录（2026-11-12）

本次变更（仅前端，后端接口未改）：

- 「写入档案」成功提交后进入已写入状态：按钮文案变为「已写入」并置灰，勾选框与「全部写入 / 只填空白项 / 全部取消」一并禁用；此时若再修改某个识别值、状态变为「新增 / 将覆盖」，按钮与勾选框恢复可用（详见第十六节）。
- `applyReview()` 增加同步防重入判断（`applying` 或 `applied` 为真时直接返回），避免快速双击触发两次请求。
- 写入成功后把本次勾选行的「档案当前值」更新为写入值、状态改为「一致」、取消勾选；因此即使识别结果中没有新增内容（全部「一致」或「未识别」），下方统计显示「将写入 0 项」，按钮保持置灰。
- 只在确实勾选了专利字段时才提交 `patent` 专业字段，避免给软著 / 商标档案提交跨类型字段而返回 422，导致「点了写入但没有写入」。

已实际执行：

| 检查 | 命令 | 结果 |
|---|---|---|
| Vue SFC 编译 | `node frontend/.sfc/check.mjs` | 15 个组件全部通过（模板 15 / 脚本 15） |
| 前端生产构建 | `node node_modules/vite/bin/vite.js build` | 68 modules，JS 224.57 kB / gzip 74.51 kB |
| 构建产物含新状态文案 | `grep` `dist/assets/*.js` | “已写入” 2 处、“本次识别结果不能重复写入” 1 处、“本次识别结果已写入档案” 1 处 |

未执行：

- **浏览器内真实点击「识别 → 写入档案 → 再点一次」**：已在第十六节通过 CDP 实际点击验证，OCR 响应为注入的模拟值。
- **服务端重复提交防护**：本次只做前端防重；后端 `PATCH /api/assets/{id}` 仍是幂等更新，未增加「同一材料只能写入一次」的数据库约束。是否需要服务端强制限制尚未确认。

## 十六、材料识别手工修改值未写入修复与交互验证（2026-11-12）

缺陷与修复：

- **现象**：在「识别结果（可修改）」列输入内容后点击「写入档案」，到档案中查看发现该字段没有写入。
- **原因**：每一行的「新增 / 将覆盖 / 一致 / 未识别」状态和勾选状态只在识别结果生成时计算一次。原本是「未识别」或「一致」的行，勾选框处于禁用状态；手工输入内容后状态没有重算，勾选框仍禁用，该值不会进入写入载荷；而按钮因其他自动勾选的行仍可点击，表现为「点了写入但输入的内容没写进去」。
- **修复**：识别结果输入框改为 `:value` + `@input="onValueInput"`，每次输入立即重算状态——有内容且与档案当前值不同 → 新增 / 将覆盖并自动勾选；清空 → 未识别并取消勾选；与原值相同 → 一致并取消勾选。
- **补充（同日）**：写入成功后若再修改某个字段、状态变为「新增 / 将覆盖」，恢复「写入档案」按钮可点击，允许把这次新修改再次提交；如果改回与档案当前值相同（「一致」）或清空（「未识别」），按钮保持置灰。`applyMessage` 同时清空，避免残留上一次的「已写入」提示。

验证方式（真实前端产物 + 真实后端，OCR 响应由 CDP 注入的 fetch 拦截返回模拟值）：

1. 临时 SQLite 写入管理员、1 个专利档案（申请号为空）、1 份证书扫描材料；
2. 启动真实 uvicorn 与前端静态代理；
3. Chrome 无头 + CDP 驱动页面，注入脚本把 `POST /api/materials/{id}/extract` 与 `GET /api/materials/{id}/extraction` 返回固定的识别结果（本机未安装 easyocr / pymupdf），其余请求（含 `PATCH /api/assets`）走真实后端。

实际执行结果（25 项检查全部通过）：

| 检查 | 结果 |
|---|---|
| 材料中心与演示材料渲染 | 通过 |
| 点击「识别」后结果表格渲染 | 9 行 |
| 「申请号」初始状态 | 「未识别」，勾选框禁用 |
| 手工输入 `CN-MOCK-999` 后 | 状态变「新增」，勾选框解除禁用并自动勾选 |
| 第一次点击「写入档案」 | 只发出 1 次 `PATCH`，请求体包含 `CN-MOCK-999` |
| 第一次写入后按钮 | 文案「已写入」，`disabled=true` |
| 后端核对 `GET /api/assets/{id}` | `application_no=CN-MOCK-999`、`patent_no=ZL2025DEMO0001` |
| 未修改时再次点击「已写入」 | 未产生新请求（累计 1 次） |
| 已写入后把申请号改为 `CN-MOCK-1000` | 状态变「将覆盖」，自动勾选；按钮文案恢复「写入档案」，`disabled=false` |
| 第二次点击「写入档案」 | 发出 1 次新请求（累计 2），请求体包含 `CN-MOCK-1000`；写入后再次变为「已写入」并置灰 |
| 后端再次核对 | `application_no=CN-MOCK-1000` |
| 再改回与当前值相同 | 状态「一致」，按钮保持「已写入」且置灰 |

同时执行：

| 检查 | 命令 | 结果 |
|---|---|---|
| Vue SFC 编译 | `node frontend/.sfc/check.mjs` | 15 个组件全部通过（模板 15 / 脚本 15） |
| 前端生产构建 | `node node_modules/vite/bin/vite.js build` | 68 modules，JS 224.72 kB / gzip 74.56 kB |

未覆盖：

- **真实 OCR / PDF 文本层识别**：本机未安装 easyocr、pymupdf，本次只验证「识别完成后人工确认与写入」链路，识别算法本身未在本环境运行。
- **服务端重复写入约束**：仍只有前端防重，后端未加「同一材料只能写入一次」约束。






## 十七、档案详情页「编辑」入口与人员关联验证（2026-11-12）

需求与确认：

- 在档案详情页「专利信息」板块增加跳转到编辑页面的按钮；
- 在「权利人与人员」板块增加人员关联入口；
- 经用户确认：「去关联」行为为**打开关联人员弹窗**，人员来源为**现有 `persons` 记录 + 现场新建**。

实现范围：

- `frontend/src/views/AssetDetailView.vue`
  - 专业信息面板标题行新增「编辑」`RouterLink`，目标 `/assets?edit=<档案 ID>`，仅 `canWrite` 用户可见；
  - 「人员」小标题旁新增「关联人员」按钮，打开抽屉：已关联人员可逐条「取消关联」；可搜索 `/api/persons` 现有人员并「关联」；可现场填写姓名与人员类型（发明人 / 设计人 / 开发人员 / 联系人）后「新建并关联」；「保存关联」调用 `PATCH /api/assets/{id}`，以 `persons: [{person_id, role, seq}]` 整组提交。
- `frontend/src/views/AssetsView.vue`
  - 页面加载后读取 `?edit=<id>`，读取档案并打开「编辑档案」抽屉（仅写权限用户）。
- `frontend/src/api.ts`
  - 新增 `createPerson`，对应 `POST /api/persons`。
- 后端未新增接口、字段或迁移：人员关联复用 `PATCH /api/assets/{id}` 既有 `persons` 更新逻辑，现场新建复用 `POST /api/persons`。

验证方式（真实前端产物 + 真实后端）：

1. 临时 SQLite 写入管理员、1 个已取得专利档案（`详情页演示案件`）和 1 个已有人员（`演示发明人乙`）；
2. 启动真实 uvicorn（8127）与 `scripts/serve_local.py` 托管 `frontend/dist`（5178）；
3. Chrome 无头 + CDP 注入登录令牌，实际点击按钮；所有请求走真实后端，未 mock 任何接口。

实际执行结果（25 项检查全部通过）：

| 检查 | 结果 |
|---|---|
| 详情页渲染案件名称与「专利信息」 | 通过 |
| 专业信息面板「编辑」链接地址 | `#/assets?edit=<id>` |
| 点击「编辑」后地址与抽屉标题 | `#/assets?edit=<id>`，「编辑档案」 |
| 编辑抽屉回填案件名称 | 「详情页演示案件」 |
| 修改我方文号为 `DEMO-EDIT-1` 并保存 | 抽屉关闭；后端 `GET /api/assets/{id}` 返回 `DEMO-EDIT-1` |
| 点击「关联人员」 | 打开「关联人员」抽屉 |
| 已有人员 `演示发明人乙` | 出现在候选列表 |
| 现场新建 `演示人员甲` 并关联 | 出现在已关联列表 |
| 保存前后端人员 | `[]` |
| 点击「保存关联」 | 抽屉关闭，详情页人员板块显示 `演示人员甲`，后端返回 `['演示人员甲']` |
| 重新打开抽屉并「取消关联」 | 已关联列表移除该人员 |
| 保存取消关联 | 后端人员恢复为 `[]`，详情页显示「尚未关联人员」 |

同时执行：

| 检查 | 命令 | 结果 |
|---|---|---|
| 后端测试 | `cd backend && .venv/Scripts/python.exe -m pytest -q` | **169 passed**（新增 `test_update_and_clear_asset_persons`：关联人员 → 返回人员；清空 `persons` → 返回空列表） |
| Vue SFC 编译 | `node frontend/.sfc/check.mjs` | 15 个组件全部通过（模板 15 / 脚本 15 / 样式块 11，失败 0） |
| 前端生产构建 | `node node_modules/vite/bin/vite.js build` | 69 modules，JS 229.67 kB / gzip 75.72 kB，CSS 27.73 kB / gzip 5.44 kB |
| 数据库迁移 | 未新增字段 | 无需迁移；`patents`、`ip_assets`、`persons` 及人员关联表沿用现有结构 |

未覆盖 / 已知限制：

- **只读用户的按钮隐藏未做浏览器点击验证**：`v-if="canWrite"` 控制前端入口，服务端仍以既有权限校验为准；本次 CDP 只用管理员账号。
- **人员关联为整组覆盖**：保存时按当前选择整体替换关联关系，没有乐观锁或冲突提示；两个用户同时编辑同一档案的人员时，后保存者会覆盖前者。是否需要冲突控制尚未确认。
- **现场新建人员只填写姓名与类型**：`persons` 接口的其他字段（如工号等，若存在）未在抽屉中维护，仍需到系统管理 / 其他入口处理。

## 十八、专利信息板块字段精简（2026-11-12）

需求：专利信息板块取消展示「申请国家 / 地区」「代理机构」「代理师」「技术领域」「摘要」。

实现：仅修改 `frontend/src/views/AssetDetailView.vue` 的 `patentLabels` 展示清单，移除上述 5 个键；同时删除摘要专用样式判断。数据库字段、API 响应和编辑接口均未改动，历史数据仍保留。

验证方式（真实前端产物 + 真实后端）：

1. 临时 SQLite 写入管理员和 1 个专利档案，档案同时填有被移除字段（国家「中国」、技术领域「边缘计算」、代理师「演示代理师」、摘要「演示摘要文本」）和保留字段；
2. 启动真实 uvicorn（8128）与前端静态代理（5179）；
3. Chrome 无头 + CDP 打开详情页，读取专业信息板块实际渲染的标签与正文。

结果（17 项检查全部通过）：

| 检查 | 结果 |
|---|---|
| 专利信息板块实际标签 | 专利类型 / 申请号 / 申请日期 / 公开号 / 公开日期 / 专利号 / 授权公告日 / 专利权期限届满日 / 法律状态（9 项） |
| 被移除的 5 个标签 | 均未渲染 |
| 被移除字段的值 | 「中国」「边缘计算」「演示代理师」「演示摘要文本」均不出现在页面正文 |
| 保留字段的值 | 申请号、公开号、专利号、授权公告日、法律状态均正常展示 |

同时执行：

| 检查 | 命令 | 结果 |
|---|---|---|
| Vue SFC 编译 | `node frontend/.sfc/check.mjs` | 15 个组件全部通过，失败 0 |
| 前端生产构建 | `node node_modules/vite/bin/vite.js build` | 69 modules，JS 229.45 kB / gzip 75.64 kB，CSS 27.73 kB |

未覆盖：

- 被移除字段在 API 中仍然返回、数据库中仍然保存；本次只调整详情页展示，未删除数据或接口字段。

## 十九、专利信息板块再移除「专利权期限届满日」（2026-11-12）

需求：在第十八节基础上，专利信息板块再取消展示「专利权期限届满日」。

实现：`frontend/src/views/AssetDetailView.vue` 的 `patentLabels` 移除 `expiry_date`。数据库字段、API 响应与编辑接口未改动。

验证：

| 检查 | 命令 | 结果 |
|---|---|---|
| Vue SFC 编译 | `node frontend/.sfc/check.mjs` | 15 个组件全部通过，失败 0 |
| 前端生产构建 | `node node_modules/vite/bin/vite.js build` | 69 modules，JS 229.41 kB / gzip 75.62 kB，CSS 27.73 kB |
| 构建产物不含该标签 | `grep -c "专利权期限届满日" frontend/dist/assets/*.js` | 0 处 |

当前专利信息板块展示：专利类型、申请号、申请日期、公开号、公开日期、专利号、授权公告日、法律状态（8 项）。

未覆盖：本次未重复启动浏览器做点击验证（结构与第十八节一致，仅减少一个标签项）；已通过构建产物不含该标签确认不会渲染。

## 二十、全部知识产权编辑抽屉新增专业字段（2026-11-12）

需求：全部知识产权的编辑抽屉允许编辑「公开号」「公开日期」「授权公告日」「法律状态」。

实现：

- `frontend/src/views/AssetsView.vue`
  - 表单新增 `publication_no`、`publication_date`、`legal_status`（`grant_date` 原已存在）；
  - 编辑时从档案详情回填，保存时写入 `patent` 对象；新建档案同样提交这些字段；
  - 三个文本 / 日期输入沿用既有控件样式，公开号与法律状态限制 `maxlength=64`（与后端 `Field(max_length=64)` 一致）。
- 后端未改动：`PatentIn` / `PatentOut` 早已包含这三个字段，`PATCH /api/assets/{id}` 以 `exclude_unset` 局部更新。
- 未新增数据库迁移。

验证证据：

| 检查 | 命令 | 结果 |
|---|---|---|
| 后端测试 | `cd backend && .venv/Scripts/python.exe -m pytest -q` | **170 passed**（新增 `test_publication_and_legal_status_editable_through_asset_update`） |
| Vue SFC 编译 | `node frontend/.sfc/check.mjs` | 15 个组件全部通过，失败 0 |
| 前端生产构建 | `node node_modules/vite/bin/vite.js build` | 69 modules，JS 230.71 kB / gzip 75.87 kB，CSS 27.73 kB |
| 浏览器 CDP | 真实后端 + 真实点击 | **24 项检查全部通过** |

CDP 验证流程与结果：

1. 临时 SQLite 写入管理员与 1 个专利档案（公开号 `CN-OLD-A`、公开日期 `2025-05-01`、法律状态 `有效`）；
2. 启动真实 uvicorn（8129）与前端静态代理（5180），Chrome 无头 + CDP 打开全部知识产权列表；
3. 点击列表行「编辑」：

| 检查 | 结果 |
|---|---|
| 编辑抽屉存在公开号 / 公开日期 / 授权公告日 / 法律状态 | 4 个输入均存在 |
| 公开号 / 公开日期 / 法律状态回填 | `CN-OLD-A` / `2025-05-01` / `有效` |
| 改为 `CN-NEW-A` / `2025-07-01` / `2025-08-20` / `实质审查中` 后保存 | 抽屉关闭 |
| 后端 `GET /api/assets/{id}` | 四个字段均为新值 |
| 未修改的申请号 / 申请日期 | 保持 `CN-EDIT-1` / `2025-01-02` |
| 新建档案抽屉 | 四个输入同样存在 |
| 新建时授权公告日早于申请日期 | 抽屉显示「授权日期不能早于申请日期」 |

未覆盖 / 说明：

- **法律状态为自由文本**：项目规格尚未确认法律状态枚举或数据字典，本次按现有 `String(64)` 字段提供文本输入，未新增下拉枚举。
- **公开日期与申请日期的先后关系未做校验**：后端仅对授权公告日晚于申请日期有校验，公开日期无此规则；是否需要由用户确认。

## 二十一、新建软著表单字段调整与证书获得日期（2026-11-12）

需求：

1. 新建档案时「知识产权类型」排在「我方文号」之前；
2. 选择软件著作权时不显示我方文号，改为录入「软件名称」「著作权人」「权利取得方式」「证书获得日期」。

经用户确认：

- 证书获得日期**新增独立字段**，不复用登记日期；
- 著作权人按**输入名称 + 权利人类型新建**并关联；
- 软件名称**复用档案主名称** `ip_assets.name`，不新增字段。

实现：

- 后端
  - `models.Copyright` 新增 `certificate_date: Date | None`；
  - `schemas.CopyrightIn` / `CopyrightOut` 新增 `certificate_date`；
  - 新增迁移 `0010_copyright_certificate_date`（列存在时跳过，兼容 0001 基线）。
- 前端 `AssetsView.vue`
  - 表单顺序改为：名称 → 知识产权类型 → 我方文号（仅非软著）→ 综合状态 → 专业字段；
  - 软著时名称标签改为「软件名称 *」，隐藏我方文号，新增著作权人、著作权人类型、权利取得方式、证书获得日期；
  - 保存软著时先调用 `POST /api/parties` 新建权利人，再以 `parties[{party_id, role: 'copyright_owner', seq}]` 创建档案；`docket_no` 固定提交 `null`；
  - 软著专业字段仅在新建时提交，编辑抽屉不回填、不修改这些字段（避免空值覆盖）。
- 前端 `AssetDetailView.vue`：软著专业信息新增「证书获得日期」展示。
- `docs/PRODUCT_SPEC.md` 软著字段清单补充「证书获得日期」。

验证证据：

| 检查 | 命令 | 结果 |
|---|---|---|
| 后端测试 | `cd backend && .venv/Scripts/python.exe -m pytest -q` | **171 passed**（新增 `test_create_copyright_with_certificate_date_and_owner`） |
| 离线综合校验 | `python scripts/verify.py --offline` | 全部通过，含 ORM 模型检查、接口审计、前后端契约、PostgreSQL 方言 DDL |
| 迁移升级 | `alembic upgrade head`（临时 SQLite 空库） | 成功到 `0010_copyright_certificate_date`，`copyrights.certificate_date` 存在 |
| 迁移降级 | `alembic downgrade 0009_drop_asset_no` | 列被删除 |
| 再次升级 | `alembic upgrade head` | 列重新建立 |
| Vue SFC 编译 | `node frontend/.sfc/check.mjs` | 15 个组件全部通过，失败 0 |
| 前端生产构建 | `node node_modules/vite/bin/vite.js build` | 69 modules，JS 232.65 kB / gzip 76.32 kB，CSS 27.73 kB |
| 浏览器 CDP | 真实后端 + 真实点击 | **28 项检查全部通过** |

CDP 验证结果：

| 检查 | 结果 |
|---|---|
| 新建抽屉标签顺序 | 案件名称 → 知识产权类型 → 我方文号 → 综合状态 → 专利类型 |
| 切换为软件著作权 | 标签变「软件名称 *」；我方文号输入消失；著作权人 / 类型 / 权利取得方式 / 证书获得日期出现 |
| 保存后 | 抽屉关闭，列表出现「演示软件著作权」 |
| 后端档案 | `ip_type=copyright`、`name=演示软件著作权`、`docket_no=null` |
| 软著字段 | `rights_mode=原始取得`、`certificate_date=2025-10-01` |
| 著作权人 | 新建并关联「演示软件权利人」（`party_type=company`） |
| 切回专利 | 我方文号重新出现，软著字段消失 |
| 编辑软著 | 标签为「软件名称 *」，无我方文号，回填原名称 |

未覆盖 / 已知限制：

- **软著编辑抽屉不修改**著作权人、权利取得方式、证书获得日期；本次按用户「新建档案时」的范围实现，编辑这些字段仍需后续需求确认。
- **权利人创建与档案创建不是同一事务**：先 `POST /api/parties` 再 `POST /api/assets`；若第二步失败，会留下一个未关联的权利人记录，需要手工清理或后续补关联。
- **不按名称去重**：每次新建软著填写著作权人都会新建一条 `parties` 记录，同名权利人可能重复；是否需要复用同名记录尚未确认。
- **权利取得方式为自由文本**：未定义枚举；**证书获得日期**与登记日期、申请日期的先后关系未做校验。

## 二十二、权利取得方式改为下拉框（2026-11-12）

需求：把新建软著表单中的「权利取得方式」从文本输入改为下拉框。

经用户确认的选项：**原始取得 / 继受取得 / 其他**；不预选默认值。

实现：`frontend/src/views/AssetsView.vue` 将 `#rights_mode` 由文本输入改为 `select`，选项为「请选择」（空值）、原始取得、继受取得、其他。字段仍写入 `copyrights.rights_mode`（String(64)），后端未改动，无迁移。

验证：

| 检查 | 命令 / 方式 | 结果 |
|---|---|---|
| Vue SFC 编译 | `node frontend/.sfc/check.mjs` | 15 个组件全部通过，失败 0 |
| 前端生产构建 | `node node_modules/vite/bin/vite.js build` | 69 modules，JS 232.78 kB / gzip 76.34 kB，CSS 27.73 kB |
| 浏览器 CDP | 真实后端 + 真实点击 | **8 项检查全部通过** |
| 控件类型 | CDP 读取 `#rights_mode` | `SELECT` |
| 选项值 | CDP 读取全部 `option` | 请选择 / 原始取得 / 继受取得 / 其他 |
| 默认值 | CDP 读取 `value` | 空（不预选） |
| 选择「继受取得」并保存 | 前端创建 + `GET /api/assets/{id}` | `copyright.rights_mode=继受取得` |

未覆盖：

- **历史自由文本值未做数据清洗**：此前若已有非上述三类的取值，下拉框打开时不会匹配任何选项；本环境无此类数据，是否需要迁移或校验尚未确认。
- 下拉框只出现在新建抽屉；软著编辑抽屉仍不编辑该字段（与第二十一节范围一致）。

## 二十三、软著编辑抽屉支持著作权人与专业字段（2026-11-12）

需求：编辑软著时也要能维护新建表单中的「软件名称」「著作权人」「权利取得方式」「证书获得日期」。

经用户确认：编辑时修改著作权人名称**更新原权利人记录**（`PATCH /api/parties/{id}`）；该权利人若被其他档案引用，其他档案会同步显示新名称。

实现：

- `frontend/src/views/AssetsView.vue`
  - `openEdit` 读取 `copyright.rights_mode`、`copyright.certificate_date` 以及第一个关联权利人（名称 / 类型 / ID）；
  - 软著专业字段不再限制为新建，编辑抽屉同样渲染并回填；
  - 保存更新时：
    - `copyright` 只提交 `rights_mode` 与 `certificate_date`，局部更新；
    - 著作权人已有记录且名称或类型变化 → `PATCH /api/parties/{id}`；
    - 原档案未关联权利人且填写了名称 → `POST /api/parties` 新建，并在档案 `PATCH` 中带上 `parties[{party_id, role: 'copyright_owner'}]`；
    - 名称留空时不做权利人变更，也不会解除已有**关联**。
- 后端 `routers/meta.py`：`update_party` 改为 `model_dump(exclude_unset=True)`。此前对权利人做部分 PATCH 会把未提交的 `contact`、`phone`、`country`、`is_default` 等重置为默认值；本次修复后只更新提交的字段。
- 未新增字段或迁移。

验证证据：

| 检查 | 命令 | 结果 |
|---|---|---|
| 后端测试 | `cd backend && .venv/Scripts/python.exe -m pytest -q` | **172 passed**（新增 `test_party_partial_update_preserves_other_fields`） |
| Vue SFC 编译 | `node frontend/.sfc/check.mjs` | 15 个组件全部通过，失败 0 |
| 前端生产构建 | `node node_modules/vite/bin/vite.js build` | 69 modules，JS 233.78 kB / gzip 76.52 kB，CSS 27.73 kB |
| 浏览器 CDP | 真实后端 + 真实点击 | **22 项检查全部通过** |

CDP 验证结果：

| 检查 | 结果 |
|---|---|
| 编辑抽屉回填 | 软件名称「演示软著甲」、著作权人「演示权利人甲」、类型「企业」、取得方式「原始取得」、证书日期 `2025-10-01` |
| 编辑软著 | 不显示我方文号 |
| 修改名称 / 著作权人 / 取得方式 / 证书日期后保存 | 抽屉关闭 |
| 后端档案 | 名称、`rights_mode=继受取得`、`certificate_date=2025-11-01` 均已更新 |
| 权利人 | 仍是原 `party_id`（未新建），名称更新 |
| 权利人其他字段 | `contact=甲`、`phone=13800000002` 未被清空 |
| 未关联权利人的软著 | 编辑时著作权人为空；填写「演示权利人乙」保存后新建并关联，取得方式「其他」、证书日期 `2025-12-01` 写入 |

未覆盖 / 说明：

- **一个软著关联多个权利人时**，编辑抽屉只回填和修改第一个，其余关联不在界面展示也不会被清空（保存时不提交 `parties`，仅新建权利人时提交）。
- 著作权人名称留空表示「不修改」，不会解除关联；如需解除关联，当前界面未提供入口，需另行确认。
- 权利人是共享基础资料，改名会影响其他引用同一权利人的档案（已由用户确认接受）。

## 二十四、软著日期统一为「授权公告日」并在列表 / 详情展示（2026-11-12）

需求：软著编辑保存「证书获得日期」后需要在页面展示，并把该字段统一显示为「授权公告日」。

实现：

- `backend/app/models.py`：`IpAsset.grant_date` 对专利返回 `patent.grant_date`，对软著返回 `copyright.certificate_date`，商标与无日期记录返回 `None`。数据库列不变，仍为 `copyrights.certificate_date`；接口字段仍为 `certificate_date`，`grant_date` 只是列表 / 详情的展示口径。
- `backend/app/routers/assets.py`：统一列表排序改用 `case` 表达式，专利取 `patents.grant_date`、软著取 `copyrights.certificate_date`；为此外连接 `copyrights` 并预加载 `IpAsset.copyright`。排序规则不变：未取得权利在前，已取得按授权公告日倒序，已取得但无日期随后，同组按更新时间倒序。
- `frontend/src/views/AssetsView.vue`：软著新建 / 编辑抽屉的日期标签由「证书获得日期」改为「授权公告日」。
- `frontend/src/views/AssetDetailView.vue`：软著专业信息展示 `certificate_date`，标签为「授权公告日」。
- `backend/tests/test_assets.py`：列表 `grant_date` 测试覆盖专利与软著；默认排序测试加入一条带 `certificate_date` 的软著，断言其插入专利之间的顺序；原测试名改为 `test_list_grant_date_uses_patent_grant_date_and_copyright_certificate_date`。
- 未新增数据库迁移。

验证证据：

| 检查 | 命令 | 结果 |
|---|---|---|
| 后端测试 | `cd backend && .venv/Scripts/python.exe -m pytest -q` | **172 passed** |
| Vue SFC 编译 | `node frontend/.sfc/check.mjs` | 15 个组件全部通过，失败 0 |
| 前端生产构建 | `node node_modules/vite/bin/vite.js build` | 69 modules，JS 233.78 kB / gzip 76.51 kB，CSS 27.73 kB |
| 浏览器 CDP | 真实 uvicorn + `frontend/dist` + 无头 Edge，真实点击 | **28 项检查全部通过** |

CDP 验证结果：

| 检查 | 结果 |
|---|---|
| 接口 `GET /api/assets` | 软著 `grant_date` 返回其 `certificate_date`（`2025-03-01`） |
| 接口默认排序 | `办理中专利, 较新专利, 软著甲, 较早专利, 无日期软著`（专利与软著按同一日期口径混排） |
| 列表表头 | 包含「授权公告日」 |
| 列表行 | 软著行显示 `2025-03-01`；无日期软著显示 `—` |
| 页面排序 | 与接口一致 |
| 编辑抽屉 | 标签「授权公告日」，回填 `2025-03-01` |
| 修改日期保存 | 改为 `2025-10-01` 后抽屉关闭，列表立即显示新日期并重排为 `办理中专利, 软著甲, 较新专利, 较早专利, 无日期软著` |
| 接口持久化 | `copyright.certificate_date == 2025-10-01` |
| 详情页 | 展示「授权公告日」及 `2025-10-01`，不再出现「证书获得日期」 |
| 新建抽屉 | 选择软件著作权后日期标签为「授权公告日」，著作权人输入仍在 |

未覆盖 / 说明：

- 商标没有对应的授权公告日，列表与详情仍显示 `—`。
- 字段语义仍来自用户录入，系统不据此推导任何法律期限；软著「授权公告日」实际存储为证书获得日期（`certificate_date`），仅是界面命名统一。
- 开发环境 `backend/var/ipms.db` 已包含迁移 `0010`，无需再次迁移；本次改动未修改表结构。

## 二十五、软著详情页字段与编辑项对齐（2026-11-12）

需求：软著信息详情页只展示与新建 / 编辑抽屉一致的字段，其余字段先隐藏。

实现：

- `frontend/src/views/AssetDetailView.vue`：`copyrightLabels` 裁剪为「权利取得方式」「授权公告日」两项，与抽屉可维护项一致；软件名称、知识产权类型、我方文号（软著隐藏）、综合状态、备注仍在基本信息板块，著作权人在「权利人与人员」板块展示。
- 其余软著字段（版本号、分类、简称、登记号 / 登记日期、申请 / 受理日期、证书编号、开发完成日期、首次发表信息、开发语言、运行平台、开发方式、软件用途、技术特点）**仅隐藏展示**，数据库与 API 不变。
- 未修改后端、未新增迁移。

验证证据：

| 检查 | 命令 | 结果 |
|---|---|---|
| 后端测试 | `cd backend && .venv/Scripts/python.exe -m pytest -q` | **172 passed** |
| Vue SFC 编译 | `node frontend/.sfc/check.mjs` | 15 个组件全部通过，失败 0 |
| 前端生产构建 | `node node_modules/vite/bin/vite.js build` | 69 modules，JS 233.24 kB / gzip 76.31 kB，CSS 27.73 kB |
| 浏览器 CDP | 真实 uvicorn + `frontend/dist` + 无头 Edge | **11 项检查全部通过** |

CDP 验证结果：

| 检查 | 结果 |
|---|---|
| 接口 | 创建并回读软著，`registration_no`、`version` 等隐藏字段仍有值 |
| 软著信息板块标签 | 仅 `['权利取得方式', '授权公告日']` |
| 字段值 | 「原始取得」「2025-06-01」正常展示 |
| 其余 16 个旧标签 | 页面文本中均未出现 |
| 基本信息 | 仍展示软件名称「演示软著详情」 |
| 权利人与人员 | 仍展示著作权人「演示著作权人」 |

未覆盖 / 说明：

- 隐藏字段目前没有任何前端查看 / 编辑入口；如需恢复展示或开放编辑，需另行确认。
- 本次只调整软著详情；专利与商标详情未改动。

## 二十六、软著详情补充著作权人 / 类型 / 备注（2026-11-12）

需求：在第二十五节的基础上，软著详情页还需要展示「著作权人」「著作权人类型」「权利取得方式」「授权公告日」「备注」。

实现：

- `frontend/src/views/AssetDetailView.vue`
  - 新增 `partyTypeLabels`（企业 / 个人 / 组织）与通用 `formatValue`；
  - `copyrightRows` 输出五项：著作权人取 `asset.parties[0].name`，著作权人类型取该权利人 `party_type`，权利取得方式取 `copyright.rights_mode`，授权公告日取 `copyright.certificate_date`，备注取 `asset.remark`；
  - 软著信息板块始终展示这五行，无数据时显示 `—`；专利 / 商标的字段列表逻辑未变；
  - 基本信息板块的「备注」行对软著隐藏，避免与软著信息板块重复；「权利人与人员」板块仍列出全部权利人。
- 未修改后端与数据库。

验证证据：

| 检查 | 命令 | 结果 |
|---|---|---|
| 后端测试 | `cd backend && .venv/Scripts/python.exe -m pytest -q` | **172 passed**（上一轮，后端本次未改动） |
| Vue SFC 编译 | `node frontend/.sfc/check.mjs` | 15 个组件全部通过，失败 0 |
| 前端生产构建 | `node node_modules/vite/bin/vite.js build` | 69 modules，JS 233.99 kB / gzip 76.50 kB，CSS 27.73 kB |
| 浏览器 CDP | 真实 uvicorn + `frontend/dist` + 无头 Edge | **17 项检查全部通过** |

CDP 验证结果：

| 检查 | 结果 |
|---|---|
| 软著信息板块标签 | `['著作权人', '著作权人类型', '权利取得方式', '授权公告日', '备注']` |
| 字段值 | `['演示著作权人', '企业', '原始取得', '2025-06-01', '仅用于详情验证']` |
| 其余 16 个软著标签 | 页面文本中均未出现 |
| 基本信息 | 仍展示软件名称；不再重复出现「备注」，标签为 `['案件名称','我方文号','知识产权类型','综合状态','创建时间']` |
| 权利人与人员 | 仍展示著作权人 |
| 无专业信息的软著 | 五个标签仍在，值为 `['—','—','—','—','—']`，不显示整块「暂未录入专业信息」空态 |
| 专利详情 | 字段列表未受影响：`['专利类型','申请号','申请日期','公开号','公开日期','专利号','授权公告日','法律状态']` |

未覆盖 / 说明：

- 一个软著关联多个权利人时，软著信息板块只展示第一个权利人；全部权利人仍在「权利人与人员」板块列出。
- 备注从基本信息板块移到软著信息板块（仅软著），专利、商标的基本信息仍保留备注。

## 二十七、材料中心上传分类默认「证书扫描件」（2026-11-12）

需求：材料中心上传材料的分类中，把「证书扫描件」放到最上面并作为默认选项。

实现：

- `frontend/src/views/MaterialsView.vue`：`categoryLabels` 调整为 `certificate_scan` 在首位；上传分类 `category` 的默认值由 `application_document` 改为 `certificate_scan`。
- 分类枚举、后端接口与数据库未改动；用户仍可在下拉框中改选其他分类。

验证证据：

| 检查 | 命令 | 结果 |
|---|---|---|
| Vue SFC 编译 | `node frontend/.sfc/check.mjs` | 15 个组件全部通过，失败 0 |
| 前端生产构建 | `node node_modules/vite/bin/vite.js build` | 69 modules，JS 233.99 kB / gzip 76.50 kB，CSS 27.73 kB |
| 浏览器 CDP | 真实 uvicorn + `frontend/dist` + 无头 Edge，真实渲染 | **7 项检查全部通过** |

CDP 验证结果：

| 检查 | 结果 |
|---|---|
| 下拉选项顺序 | `证书扫描件, 申请文件, 官方通知, 软件说明书, Logo 图样, 年费缴费凭证, 发票附件, 其他` |
| 第一项 | `certificate_scan / 证书扫描件` |
| 默认选中值 | `certificate_scan` |
| 上传材料面板 | 正常渲染 |

未覆盖 / 说明：

- 本次未在浏览器中实际上传文件（只验证默认分类与顺序）；上传接口与文件校验逻辑未改动。
- 后端 pytest 本次未重跑（后端代码零改动）；上一轮执行结果为 172 passed。

## 二十八、材料中心备注字段（2026-11-12）

需求：材料中心页面增加备注字段并在页面展示。

实现：

- 后端已有 `materials.remark`（`Text`）、上传接口 `Form(remark)`、`MaterialOut.remark` 与 `PATCH /api/materials/{id}` 的 `remark`，无需迁移；本次补充接口回归测试。
- `frontend/src/views/MaterialsView.vue`
  - 上传面板新增「备注（可选，最多 500 字）」输入框，上传时随表单提交，成功后清空；
  - 材料列表新增「备注」列，无备注显示 `—`，空态 / 加载行列数同步为 7；
  - 材料查看弹窗标题区展示「备注：…」。
- `backend/tests/test_integrity_and_files.py` 新增 `test_material_upload_persists_remark_and_lists_it`。

验证证据：

| 检查 | 命令 | 结果 |
|---|---|---|
| 后端测试 | `cd backend && .venv/Scripts/python.exe -m pytest -q` | **173 passed**（新增 1 项） |
| Vue SFC 编译 | `node frontend/.sfc/check.mjs` | 15 个组件全部通过，失败 0 |
| 前端生产构建 | `node node_modules/vite/bin/vite.js build` | 69 modules，JS 234.48 kB / gzip 76.64 kB，CSS 27.73 kB |
| 浏览器 CDP | 真实 uvicorn + `frontend/dist` + 无头 Edge，真实上传 | **19 项检查全部通过** |

CDP 验证结果：

| 检查 | 结果 |
|---|---|
| 上传面板 | 出现备注输入框，占位「备注（可选，最多 500 字）」 |
| 列表表头 | `案件名称, 文件名称, 分类, 大小, 标识, 备注, 操作` |
| 真实上传 | 页面内选择案件、选择 `sample.png`、填写备注后点击上传成功 |
| 列表展示 | 新行分类为「证书扫描件」，备注列为「证书原件存放于财务柜」 |
| 无备注材料 | 备注列显示 `—` |
| 上传后 | 备注输入框已清空 |
| 查看弹窗 | 标题区展示「备注：证书原件存放于财务柜」 |

未覆盖 / 说明：

- 备注只在新增上传时录入；界面暂未提供修改 / 清除已有材料备注的入口（后端 `PATCH` 已支持，未接前端）。
- 备注最多 500 字为前端输入限制；后端 `Text` 字段本身未加长度约束。

> 上述「暂未提供修改备注入口」已由第二十九节补齐。

## 二十九、材料中心上传面板优化与「修改材料」抽屉（2026-11-12）

需求：优化上传材料板块 UI（当前交互与展示不直观）；在操作栏增加修改入口，支持修改备注和更换文件。

已确认事项：更换文件后**保留旧文件**——数据库改指新文件，旧文件仍留在存储层且不被引用；审计日志记录旧对象键与哈希，可人工恢复。

实现：

- 后端 `backend/app/routers/materials.py`
  - 抽出 `_validate_and_store()`，上传与更换共用同一套文件校验、大小限制与存储写入逻辑，错误码保持一致（413 / 415 / 422）。
  - 新增 `POST /api/materials/{material_id}/replace`（multipart：`file` 必填、`remark` 可选）。需写权限；材料不存在 / 已删除 / 不可见返回 404；文件校验失败返回 413 / 415 / 422。
  - 更换时：写入新对象、更新原始文件名 / 扩展名 / MIME / 大小 / 哈希；仅当显示名称原本等于旧原始文件名时跟随新文件名，人工改过的显示名称保留；`remark` 传入时更新。
  - 旧文件不删除，审计 `action=replace_file` 记录旧与新两组 `storage_key` / `sha256` / `size_bytes` / `original_name`。
  - 文件已更换，旧识别结果不再适用：`extraction_status` 重置为 `none`，`extraction_kind/source/fields/text/error/started_at/finished_at` 清空。
  - 事务失败时回滚数据库并删除本次新写入的对象，避免产生无引用文件。
- 后端 `backend/tests/test_integrity_and_files.py`
  - `test_replace_material_file_keeps_old_blob_and_resets_extraction`：旧文件仍在存储层、数据库指向新键、识别状态与字段清空、备注更新、审计存在。
  - `test_viewer_cannot_replace_material_file`：只读账号 403。
- 前端 `frontend/src/api.ts`：新增 `updateMaterial`（PATCH）与 `replaceMaterialFile`（POST `/replace`）。
- 前端 `frontend/src/views/MaterialsView.vue`
  - 上传面板改为带标签的两列网格：关联案件、分类、文件、备注；文件选择后显示文件名与大小并提供「清除」；上传按钮在案件 / 文件缺失或上传中禁用；成功后显示「已上传「文件名」」。
  - 行操作新增「修改」（仅可写角色），打开右侧抽屉：展示当前材料名称、原始文件名、大小、分类与关联案件；可修改备注；可选「更换文件」并提示「不选择文件则只更新备注；更换后旧文件保留在存储层，识别结果会重置」；错误在抽屉内展示，保存中禁用按钮，Esc / 遮罩可关闭。
  - 仅改备注调用 PATCH；选择了新文件调用替换接口并同时提交备注；成功后关闭抽屉、刷新列表并显示结果提示。

验证证据：

| 检查 | 命令 | 结果 |
|---|---|---|
| 后端测试 | `cd backend && .venv/Scripts/python.exe -m pytest -q` | **175 passed**（新增 2 项），1 条 starlette 弃用警告 |
| Vue SFC 编译 | `node frontend/.sfc/check.mjs` | 15 个组件全部通过，失败 0 |
| 前端生产构建 | `node node_modules/vite/bin/vite.js build` | 69 modules，JS 238.91 kB / gzip 77.80 kB，CSS 29.71 kB |
| 浏览器 CDP | 真实 uvicorn + 临时 SQLite + `frontend/dist` + 无头 Edge | **36 项检查全部通过** |

CDP 验证结果（真实选择案件、上传文件、点击行内「修改」并保存）：

| 检查 | 结果 |
|---|---|
| 上传面板字段 | 关联案件 / 分类 / 文件 / 备注均已展示 |
| 默认分类 | `certificate_scan`（证书扫描件） |
| 初始按钮状态 | 案件与文件未齐备时上传按钮禁用 |
| 选择案件 | 下拉出现匹配项，选择后显示案件名称 |
| 选择文件 | 显示 `upload.png · 20 B` 与「清除」 |
| 真实上传 | 成功提示「已上传「upload.png」」，列表展示备注「端到端备注」 |
| 修改入口 | 行内「修改」可点击，抽屉展示「修改材料」、关联案件并回填现有备注 |
| 只改备注 | 提示「已更新「upload.png」的备注」，抽屉关闭，列表备注更新；旧备注不再出现 |
| 更换提示 | 选择新文件后显示「将替换为：bad.txt · 10 B」与「取消更换」 |
| 错误状态 | 上传 `.txt` 保存时抽屉内显示「不支持的文件类型：.txt」，抽屉保持打开 |
| 成功更换 | 提示「已更换「upload.png」的文件」，列表显示 `replacement.png`，备注保留 |
| 存储与数据库 | 数据库指向新对象键；新文件存在；旧对象键文件仍存在 |
| 识别状态 | 更换后 `extraction_status` 为 `none` |
| 审计 | 存在 `object_type=material&action=replace_file` 且 `object_id` 为该材料 ID 的记录 |

未覆盖 / 说明：

- 旧文件保留在存储层但没有清理 / 恢复界面或自动回收策略；恢复需按审计日志中的旧对象键人工处理。
- 更换文件只允许一个文件；如需多文件请逐条修改。
- 显示名称跟随新文件名的前提是它仍等于旧原始文件名；人工改过的显示名称不会被覆盖。
- 本次未在无头浏览器中验证 Esc 关闭抽屉与移动端单列布局（仅由 SFC 编译、构建和模板结构覆盖）。

> 本节记录的「内嵌上传网格面板」已按用户后续要求改为页头「上传资料」按钮 + 弹窗，见第三十节。

## 三十、上传入口改为页头按钮与弹窗（2026-11-12）

需求：材料中心页面只展示一个「上传资料」按钮，点击后在弹出页面中输入；同时优化「选择文件」按钮。

实现（`frontend/src/views/MaterialsView.vue`）：

- 移除页面内嵌的上传面板；页头操作区在搜索框与「查询」右侧新增主按钮「上传资料」，仅可写角色可见。
- 点击后从右侧打开「上传资料」抽屉：关联案件（必选）、分类（默认证书扫描件）、文件（必选）、备注（可选，最多 500 字）；未选案件 / 文件或上传中时提交按钮禁用；错误在抽屉内展示；遮罩、Esc、取消均可关闭（上传中不可关闭）。
- 上传成功后抽屉关闭，页面顶部显示绿色结果横幅「已上传「文件名」」并刷新列表；结果横幅同时用于修改备注 / 更换文件后的提示。
- 文件选择改为自定义控件：隐藏原生 `<input type="file">`，显示「选择文件」按钮 + 已选文件名与大小 + 「清除」；未选择时显示「未选择文件」。修改抽屉同样改为「选择新文件」按钮，未选择时提示「当前文件保持不变」。
- 通过 `/materials?upload=1` 进入时（工作台入口）直接打开上传抽屉；若带 `asset` 参数则预选该案件。
- 未新增接口与数据库字段；上传仍调用既有 `POST /api/materials`。

验证证据：

| 检查 | 命令 | 结果 |
|---|---|---|
| Vue SFC 编译 | `node frontend/.sfc/check.mjs` | 15 个组件全部通过，失败 0 |
| 前端生产构建 | `node node_modules/vite/bin/vite.js build` | 69 modules，JS 239.92 kB / gzip 77.93 kB，CSS 29.19 kB |
| 浏览器 CDP | 真实 uvicorn + 临时 SQLite + `frontend/dist` + 无头 Edge（1440×900） | **28 项检查全部通过**，并截图核对弹窗布局 |

CDP 验证结果：

| 检查 | 结果 |
|---|---|
| 页面入口 | 页头展示「上传资料」按钮，页面内不再存在内嵌上传表单 |
| 打开弹窗 | 点击后抽屉标题为「上传资料」，包含关联案件 / 分类 / 文件 / 备注 |
| 默认分类 | `certificate_scan`（证书扫描件） |
| 初始状态 | 未选案件与文件时提交按钮禁用 |
| 文件控件 | 显示「选择文件」按钮；未选择时显示「未选择文件」 |
| 选择案件 | 下拉出现匹配项，选择后显示案件名称 |
| 选择文件 | 显示 `upload.png · 21 B` 与「清除」 |
| 提交 | 案件与文件齐备后按钮可用；上传成功提示「已上传「upload.png」」，弹窗关闭 |
| 列表 | 新行展示文件与备注「弹窗上传备注」 |
| 修改抽屉 | 文件区显示「选择新文件」按钮；未选时提示「当前文件保持不变」；选择后显示「将替换为：new.png · 22 B」 |

未覆盖 / 说明：

- 后端改动为零，本次未重跑 pytest；最近一次结果为 175 passed。
- 未实测拖拽上传、键盘 Tab 顺序与窄屏布局；原生文件对话框在无头环境中由 CDP 直接设值替代。

## 三十一、操作按钮统一移到标题下方工具栏（2026-11-12）

需求：材料中心把右上角的「上传资料」和「查询」移到「材料中心」标题下方、数据表上方，上传按钮在前；其他页面按同样方式调整。

实现：

- `frontend/src/views/MaterialsView.vue`：工具栏顺序改为 **上传资料 → 搜索框 → 查询**，位于标题与数据表之间。
- 其余带页头操作按钮的页面统一处理，主操作按钮放在工具栏首位：
  - `AssetsView.vue`：＋ 新建档案 → 搜索 / 类型 / 状态 / 查询 / 重置
  - `FeesView.vue`：＋ 登记费用 → 搜索框 → 查询
  - `DatesView.vue`：＋ 新建日期事项（下方为重要说明与表格）
  - `TrademarksView.vue`：＋ 新建商标（下方为卡片列表）
  - `UsersView.vue`：＋ 新建用户（用户页签工具栏首位，搜索框其后）
  - `MetaView.vue`：新建按钮（随页签变化）→ 搜索框 → 条数提示
  - `DashboardView.vue`：新建案件 / 上传材料 / 导入档案 / 登记费用 四个按钮移入工具栏
- 页头不再包含操作按钮；`frontend/src/styles.css` 删除已无引用的 `.head-actions` 规则。没有改动业务逻辑、接口或权限。

验证证据：

| 检查 | 命令 | 结果 |
|---|---|---|
| Vue SFC 编译 | `node frontend/.sfc/check.mjs` | 15 个组件全部通过，失败 0 |
| 前端生产构建 | `node node_modules/vite/bin/vite.js build` | 69 modules，JS 239.71 kB / gzip 77.85 kB，CSS 29.12 kB |
| 浏览器 CDP | 真实 uvicorn + 临时 SQLite + `frontend/dist` + 无头 Edge（1440×900） | **39 项检查全部通过**，并截图核对材料中心布局 |

CDP 验证结果：

| 页面 | 检查结果 |
|---|---|
| 材料中心 | 标题区无按钮；工具栏首个按钮为「上传资料」且唯一；顺序为「上传资料 → 搜索框 → 查询」；工具栏顶部位于数据表上方；上传按钮仍可打开弹窗 |
| 全部知识产权 | 标题区无按钮；工具栏首个为「＋ 新建档案」 |
| 费用台账 | 标题区无按钮；工具栏首个为「＋ 登记费用」 |
| 日期台账 | 标题区无按钮；工具栏首个为「＋ 新建日期事项」 |
| 商标 / Logo | 标题区无按钮；工具栏首个为「＋ 新建商标」 |
| 系统管理 | 标题区无按钮；工具栏首个为「＋ 新建用户」 |
| 基础资料 | 标题区无按钮；工具栏首个为「＋ 新建权利人」；工具栏位于数据表上方 |
| 工作台 | 标题区无按钮；工具栏首个为「＋ 新建案件」 |

未覆盖 / 说明：

- 未做窄屏（<760px）截图；工具栏使用全局 `.toolbar` 的 `flex-wrap`，预期自动换行。
- 只读角色下按钮显隐仍沿用原有 `canWrite` / `canAdmin` 判断，未改权限逻辑；本次以 admin 账号验证。

## 三十二、修改材料抽屉字段顺序与「可选」文案（2026-11-12）

需求：修改材料页面把「更换文件」放到「备注」上面，「关联案件」放在最上面；去掉「（可选）」字样，但该字段事实上仍为可选。

实现（`frontend/src/views/MaterialsView.vue`）：

- 抽屉字段顺序改为：关联案件 → 更换文件 → 备注。
- 「更换文件（可选）」标签改为「更换文件」；备注输入框占位文案由「可选，最多 500 字」改为「最多 500 字」。
- 行为不变：不选择文件时只更新备注，选择文件时替换文件并同时提交备注；提示「不选择文件则只更新备注；更换后旧文件保留在存储层，识别结果会重置」保留。

验证证据：

| 检查 | 命令 | 结果 |
|---|---|---|
| Vue SFC 编译 | `node frontend/.sfc/check.mjs` | 15 个组件全部通过，失败 0 |
| 前端生产构建 | `node node_modules/vite/bin/vite.js build` | 69 modules，JS 239.69 kB / gzip 77.85 kB，CSS 29.12 kB |
| 浏览器 CDP | 真实 uvicorn + 临时 SQLite + `frontend/dist` + 无头 Edge（1440×900） | **9 项检查全部通过**，并截图核对抽屉 |

CDP 验证结果：

| 检查 | 结果 |
|---|---|
| 字段顺序 | `['关联案件', '更换文件', '备注']` |
| 关联案件位置 | 抽屉第一个表单项，位于最上方 |
| 「（可选）」 | 抽屉文本中不存在 |
| 「可选」字样 | 抽屉文本中不存在 |
| 可选行为提示 | 仍显示「不选择文件则只更新备注」 |
| 备注占位 | `最多 500 字` |

未覆盖 / 说明：

- 后端无改动，未重跑 pytest；最近一次为 175 passed。

## 三十三、工作台搜索框缩小并前移到「新建案件」左侧（2026-11-12）

需求：把工作台页面的搜索框缩小，放到「新建案件」左侧。

实现（`frontend/src/views/DashboardView.vue`）：

- 删除原先独占一行、全宽的 `.workbench-search` 区块，把 `.search-input-wrap` 移入标题下方的 `.toolbar`，作为工具栏第一个元素，其后才是「＋ 新建案件」等操作按钮。
- 搜索框固定宽度 420px（`flex:none`），输入框字号 13px；下拉结果仍绝对定位在输入框下方，宽度与输入框一致。
- 搜索结果右侧原 `.badge` 改为专用 `.search-action` 胶囊按钮：边框 + 浅蓝底，悬停时反色；`flex:0 0 auto` 与 `white-space:nowrap` 保证「查看案件」四个字始终单行、不被长名称压缩。案件名称与文号改为单行省略号截断。
- 搜索逻辑、占位文案、下拉内容与点击跳转均未改动；没有改动接口、权限或其他页面。

验证证据：

| 检查 | 命令 | 结果 |
|---|---|---|
| Vue SFC 编译 | `node frontend/.sfc/check.mjs` | 15 个组件全部通过，失败 0 |
| 前端生产构建 | `node node_modules/vite/bin/vite.js build` | 69 modules，JS 239.65 kB / gzip 77.83 kB，CSS 29.49 kB |
| 浏览器 CDP | 真实 uvicorn + 临时 SQLite + `frontend/dist` + 无头 Edge（1440×900） | **18 项检查全部通过**，并截图核对布局、超长名称与按钮 |

CDP 验证结果：

| 检查 | 结果 |
|---|---|
| 旧独立搜索区块 | `.workbench-search` 已不存在 |
| 工具栏首元素 | `.search-input-wrap` |
| 搜索框宽度 | 420px（输入框与容器实测均为 420px） |
| 与「＋ 新建案件」关系 | 输入框右边界在按钮左边界之前，两者同一行 |
| 模糊搜索 | 输入「超长案件」返回 1 条匹配结果 |
| 查看案件按钮 | 文案为「查看案件」；`white-space:nowrap`；单行高 26px；实测宽 68px；`flex-shrink:0`；完整位于下拉框内且与结果行垂直居中 |
| 超长案件名称 | `text-overflow:ellipsis` 生效（`scrollWidth > clientWidth`），名称右边界在按钮左侧 |
| 搜索下拉宽度 | 420px，与搜索框一致 |

未覆盖 / 说明：

- 后端无改动，未重跑 pytest；最近一次为 175 passed。
- 未做窄屏（<760px）截图；工具栏沿用全局 `flex-wrap`。

## 三十四、openEuler + PostgreSQL 生产部署（2026-11-16）

部署目标：`10.20.0.18`，openEuler 22.03 LTS-SP4，PostgreSQL 13.23，Nginx 1.21.5，SELinux Disabled，firewalld 运行中。

实际安装：

- 系统 Python 3.9.9 不满足代码要求，从源码编译 Python 3.12.10 到 `/opt/python3.12`，系统 `python3` 保持不变；
- 初始发布版本：`20261116-1142`；后续通过 `deploy.sh` 升级到 `20261116-180105`，`/opt/ipms/current` 当前指向后者；
- 虚拟环境：`/opt/ipms/venv`；运行用户：`ipms`；
- 配置：`/etc/ipms/ipms.env`（root:ipms，640）；上传文件：`/var/lib/ipms/storage`；
- 前端静态文件：`/usr/share/nginx/ipms`；Nginx 配置：`/etc/nginx/conf.d/ipms.conf`；systemd：`ipms.service`。

验证证据：

| 检查 | 命令/方式 | 结果 |
|---|---|---|
| PostgreSQL 初始化 | `postgresql-setup --initdb` + `systemctl enable --now postgresql` | 服务 active/enabled |
| 真实 PostgreSQL 迁移 | `alembic upgrade head` | 从基线升级到 `0010_copyright_certificate_date (head)` |
| 表数量 | `information_schema.tables` | public schema 20 张表（19 张业务表 + `alembic_version`） |
| 服务运行用户 | `ps -o user= -p <MainPID>` | `ipms`，非 root |
| 监听端口 | `ss -lntp` | Nginx `0.0.0.0:80`；uvicorn `127.0.0.1:8000`；PostgreSQL `127.0.0.1` 和 `10.20.0.18:5432` |
| 健康检查 | `GET http://127.0.0.1:8000/health` | `{"status":"ok","app":"知识产权管理系统"}` |
| 站点首页 | `GET http://10.20.0.18/` | 200，引用 `assets/index-ChV9L9QC.js` |
| 浏览器登录 | 无头 Edge + CDP 访问部署站点 | **8 项检查全部通过**：登录页、表单、提交、工作台、数据加载、令牌、路由、`/api/auth/me` 200 |
| 204 响应 | 登录后 `POST /api/auth/logout` | 204，响应体长度 0；重新登录 200 |
| 开机自启 | `systemctl is-enabled ipms nginx postgresql` | 三者均 `enabled` |
| 防火墙 | `firewall-cmd --list-rich-rules` | 对 `10.20.0.0/24`、`172.20.0.0/22`、`192.168.203.0/24` 放行 80 和 5432 |

部署中发现并修复的缺陷：

1. **FastAPI 204 路由启动失败**：`requirements.txt` 原固定 `fastapi==0.115.6`，该版本会把返回注解 `-> None` 推断为响应模型，导致所有 204 路由在导入时触发 `AssertionError`。已将依赖改为本地测试使用的 `fastapi==0.115.14`，并在 8 个 204 路由上显式声明 `response_model=None`（`admin.py`、`assets.py`、`auth.py`、`fees.py`、`materials.py`、`meta.py`）。修改后 `pytest -q` 175 passed，服务正常启动。
2. **openEuler PostgreSQL 13 默认认证不匹配**：`pg_hba.conf` 默认 `host ... ident`，`password_encryption` 默认 `md5`。已改为 `scram-sha-256`，并用 `SET password_encryption='scram-sha-256'` 重设应用账号密码。
3. **配置目录权限**：`/etc/ipms` 必须为 `root:ipms 750`，否则 `ipms` 用户无法读取环境文件；已修正。
4. **客户端网段变化**：客户端从 `172.20.0.0/22` 切换到 `192.168.203.0/24` 后，firewalld 未放行 80，表现为能 ping 通、SSH 能连但网页打不开；已补充 `192.168.203.0/24` 规则，网页和登录接口恢复 200。

管理员初始密码生成后保存在服务器 `/root/ipms-admin-password.txt`（600，root only），未写入仓库或日志。

未覆盖 / 说明：

- 生产 PostgreSQL 上尚未验证材料上传/下载、Excel 导入导出、证书识别；备份已配置并完成恢复演练（见第三十五节）。
- 未配置 HTTPS；当前仅内网 HTTP，并已用 firewalld 限制来源网段。
- 未配置监控与日志采集。

## 三十五、生产自动备份与恢复演练（2026-11-16）

实现：

- `/usr/local/sbin/ipms-backup.sh`：检查磁盘余量（至少 2 GiB）→ `pg_dump -Fc` → 校验 dump 可被 `pg_restore -l` 读取 → 打包 `/var/lib/ipms/storage` → 校验 tar → 权限 600 → 删除 14 天前备份；
- `/etc/systemd/system/ipms-backup.service`：oneshot，root 执行；
- `/etc/systemd/system/ipms-backup.timer`：每天 02:00，`Persistent=true`，随机延迟 15 分钟；
- 备份目录：`/var/backups/ipms`。

验证证据：

| 检查 | 结果 |
|---|---|
| 手动执行 | `systemctl start ipms-backup.service` 成功，退出码 0 |
| 数据库备份 | `db-20261116-110657.dump`，56 KB，权限 600 |
| 文件存储备份 | `storage-20261116-110657.tar.gz`，4.0 KB，权限 600，tar 可读取 |
| 定时器 | `ipms-backup.timer` 为 enabled/active，下次执行 2026-11-17 02:03 |
| 恢复演练 | 把 dump 恢复到临时库 `ipms_restore_check`：20 张 public 表、`0010_copyright_certificate_date`、1 个用户；随后删除临时库 |
| 生产库影响 | 恢复演练未触碰生产库；应用服务保持运行 |

未覆盖 / 说明：

- 当前上传目录为空，文件存储备份只验证了空目录 tar；有实际上传文件后需要再做一次文件恢复演练。
- 14 天保留策略已写入脚本，但尚未等到自然过期；未构造过期文件测试删除逻辑。
- 备份位于本机同一块磁盘，只能防误删/逻辑损坏，不能防整机磁盘故障；如需更高保障，应将 `/var/backups/ipms` 同步到另一台机器或对象存储。

## 三十六、退出登录仅撤销当前会话（2026-11-16）

需求：退出登录只退出当前这台设备，不影响同一账号在其他设备上的登录。

实现：

- `backend/app/routers/auth.py` 的 `logout` 不再撤销该用户全部 `AuthSession`，改为根据请求携带的 Bearer token 计算 `token_hash`，只把当前会话标记为已撤销；
- 审计摘要由“退出登录”改为“退出当前会话”；
- 新增测试 `test_logout_revokes_only_current_session`：连续登录两次，退出第一个 token 后，第一个 token 返回 401，第二个 token 仍可访问 `/api/auth/me`。

验证证据：

| 检查 | 命令/方式 | 结果 |
|---|---|---|
| 自动化测试 | `pytest -q` | **176 passed** |
| 生产部署 | 发布 `20261116-1142`，systemd 重启 | `ipms` active，`/health` 正常 |
| 生产双会话验证 | 经 Nginx 登录两次 → 退出 A → 查 A/B | 退出 204；A `/api/auth/me` 401；B `/api/auth/me` 200 |
| 浏览器登录（新密码） | 无头 Edge 访问部署站点 | **5 项检查全部通过**：登录页、提交、工作台、无“登录已失效”、数据加载 |
| 清理验证会话 | 退出 B | 204 |

同时按用户要求重置了 `admin` 密码，并撤销了重置前所有活动会话。新密码仅保存在服务器 `/root/ipms-admin-password.txt`（600，root only），未写入本文件或应用日志。

未覆盖 / 说明：

- 生产验证使用两个 API 会话模拟两台设备，未用两台真实浏览器同时点击退出；
- 密码重置会使重置前签发的所有 token 立即失效，其他设备需要重新登录。

## 三十七、发布与回滚脚本（2026-11-16）

新增：

- `scripts/deploy.sh`：本机执行，负责 pytest → 前端构建 → tar 打包 → scp 上传 → 服务器备份 → 解压 → pip 安装 → Alembic 迁移 → 切换 `current` → 更新 Nginx 静态文件 → 重启 → 健康检查；
- `scripts/rollback.sh`：本机执行，支持 `--list` 查看版本、默认回滚到当前版本的前一个版本、指定版本回滚；只回滚代码和前端，不自动恢复数据库。

验证证据：

| 检查 | 命令 | 结果 |
|---|---|---|
| 脚本语法 | `bash -n scripts/deploy.sh`、`bash -n scripts/rollback.sh` | 均通过 |
| 版本列表（只读） | `bash scripts/rollback.sh --list` | 正确显示版本目录 |
| 帮助信息 | `bash scripts/deploy.sh --help`、`bash scripts/rollback.sh --help` | 正常输出 |
| 完整发布 | `bash scripts/deploy.sh` | 成功部署 `20261116-180105`：测试、构建、备份、上传、解压、依赖检查、迁移、切版本、复制前端、重启、健康检查全部通过 |

未覆盖 / 说明：

- `deploy.sh` 已于 2026-11-16 完整执行一次并成功；后续发布仍应观察备份、迁移和健康检查输出；
- `rollback.sh` 的完整切换未执行；只验证了只读的版本列表和参数校验；
- 两个脚本默认使用本机 SSH 私钥 `$HOME/.ssh/ipms_deploy`，如密钥位置变化需设置 `DEPLOY_KEY`。

## 三十八、Navicat SSH 隧道配置（2026-11-16）

问题：Navicat Premium 17 使用 SSH 隧道连接 PostgreSQL 时提示 `server closed the connection unexpectedly`。

排查：

- `/var/log/secure` 显示 SSH 密码登录成功，但紧接着记录：
  `refused local port forward: originator 127.0.0.1 port 0, target localhost port 5432`；
- `sshd -T` 显示 `allowtcpforwarding no`，`/etc/ssh/sshd_config` 第 151 行显式关闭了 TCP 转发。

处理：

```bash
cp -a /etc/ssh/sshd_config /etc/ssh/sshd_config.bak-<时间>
sed -i 's/^AllowTcpForwarding no$/AllowTcpForwarding local/' /etc/ssh/sshd_config
sshd -t
systemctl reload sshd
```

验证：

- `sshd -T` 返回 `allowtcpforwarding local`；
- 本机执行 `ssh -N -L 127.0.0.1:15432:127.0.0.1:5432 root@10.20.0.18` 成功建立本地监听；
- 本节操作时未开放 5432 到局域网；后续按用户要求改为直连，见第三十九节。

说明：Navicat 常规页签必须填写数据库侧地址 `127.0.0.1:5432`、库名 `ipms`、用户 `ipms` 和数据库密码；SSH 页签的密码是服务器 root 密码，两者不同。

## 三十九、PostgreSQL 内网直连（2026-11-16）

需求：客户端直接连接 `10.20.0.18:5432`，不再使用 SSH 隧道。

实现：

- `/var/lib/pgsql/data/postgresql.conf`：`listen_addresses = '127.0.0.1,10.20.0.18'`；
- `/var/lib/pgsql/data/pg_hba.conf`：对 `192.168.203.0/24`、`172.20.0.0/22`、`10.20.0.0/24` 增加 `host ipms ipms ... scram-sha-256`；
- firewalld：同三个内网网段放行 TCP 5432；
- 修改前已备份 `postgresql.conf.bak-*`、`pg_hba.conf.bak-*`；
- PostgreSQL 重启后，`ipms` 服务自动恢复，健康检查正常。

验证证据：

| 检查 | 方式 | 结果 |
|---|---|---|
| 监听地址 | `ss -lntp` | `10.20.0.18:5432` 和 `127.0.0.1:5432` |
| 服务器侧验证 | `psql -h 10.20.0.18 -U ipms -d ipms` | 返回 `ipms|ipms` |
| 本机连通性 | `Test-NetConnection 10.20.0.18 -Port 5432`（源地址 192.168.203.88） | `TcpTestSucceeded: True` |
| 本机客户端验证 | 本机 psycopg 3.2.3 直连 | 连接成功，`PostgreSQL 13.23`，`ip_assets` 可查询 |
| 应用健康 | `GET /health` | 正常 |

Navicat 设置：不勾选 SSH 隧道；主机 `10.20.0.18`、端口 `5432`、初始数据库 `ipms`、用户 `ipms`、密码取自 `/etc/ipms/ipms.env`。

风险说明：5432 已对内网受控网段开放，必须保持强密码；如只需查看，建议另建只读账号。不要对公网或不受控网段开放 5432。

## 四十、PDF 预览与文本识别依赖 PyMuPDF（2026-11-16）

问题：材料中心打开 PDF 时提示“服务器未安装 pymupdf，无法解析/生成预览”。

处理：

- 在服务器共享虚拟环境安装 `pymupdf==2.1`；
- 将 `pymupdf==2.1` 写入 `backend/requirements.txt`，并同步到当前版本目录；
- 重启 `ipms` 服务。

验证证据：

| 检查 | 方式 | 结果 |
|---|---|---|
| 依赖导入 | `/opt/ipms/venv/bin/python -c "import pymupdf"` | 版本 `2.1` |
| PDF 预览 | `GET /api/materials/<id>/preview?page=0` | 200，`image/png`，85,993 字节，`X-Page-Count: 1` |
| PDF 识别 | `POST /api/materials/<id>/extract` 后轮询 | `extraction_status=succeeded`，`source=text-layout` |
| 识别字段 | 识别结果 | 名称、申请日、授权日；提示“未识别到专利号/申请号，请人工核对” |
| 应用健康 | `/health` | 正常 |

未覆盖 / 说明：

- 只有文字层 PDF 已验证；扫描件 PDF 和 JPG/PNG 仍依赖 EasyOCR，服务器未安装 easyocr，会继续提示“未安装 easyocr”；
- DOCX 识别不支持，仍返回“暂不支持识别 docx 类型文件”；
- 识别结果只是建议值，必须人工确认后写入档案。

## 四十一、Excel 导入 500：NumPy CPU baseline 不兼容（2026-11-16）

问题：工作台导入 XLSX 时返回 500；服务端堆栈入口为：

```text
File ".../app/routers/admin.py", line 387, in import_assets
    from openpyxl import load_workbook
...
RuntimeError: NumPy was built with baseline optimizations:
(X86_V2) but your machine doesn't support:
(X86_V2).
```

原因：安装 PyMuPDF 2.1 时被依赖解析带入了 `numpy 2.5.5`，该 wheel 需要 X86_V2 基线，而服务器 CPU 不支持；`openpyxl` 在导入时会尝试导入 numpy，导致整个导入接口 500。

处理：

- 安装 `numpy==1.26.4`；
- 在 `backend/requirements.txt` 中显式固定 `numpy==1.26.4` 并注释原因；
- 同步到当前版本目录，重启 `ipms`。

验证证据：

| 检查 | 结果 |
|---|---|
| `import numpy, openpyxl, pymupdf` | 成功；NumPy 1.26.4、openpyxl 3.1.5、PyMuPDF 2.1 |
| `openpyxl.load_workbook` | 读写临时 XLSX 成功 |
| 导入模板接口 | `GET /api/import/assets/template.xlsx` 返回 200，6,047 字节 |
| 应用健康 | 正常 |

未覆盖 / 说明：

- 尚未用用户的实际 XLSX 再次执行完整导入；需用户在页面重试，若仍失败再按新的服务端堆栈定位字段或格式问题；
- 固定 NumPy 1.26.4 是为了兼容当前服务器 CPU，不应随意升级到 NumPy 2.5+。

## 四十二、EasyOCR 图片识别（2026-11-16）

需求：为扫描件 PDF、JPG/PNG 提供 OCR 能力，并提前创建模型目录。

安装：

- 模型目录：`/opt/ipms/.EasyOCR/model`、`/opt/ipms/.EasyOCR/user_network`，属主 `ipms:ipms`，权限 750；
- 依赖：`torch==2.5.1+cpu`、`torchvision==0.20.1+cpu`、`easyocr==1.7.2`、`numpy==1.26.4`、`scipy==1.13.1`、`scikit-image==0.24.0`、`opencv-python-headless==4.11.0.86`；
- 模型：`craft_mlt_25k.pth`（80 MB）、`zh_sim_g2.pth`（21 MB），从本机缓存复制到服务器，属主 `ipms:ipms`，权限 640；
- `backend/requirements-ocr.txt` 记录可复现的安装清单；
- `app/extraction.py` 的 Reader 增加 `quantize=False`。

问题与修复：

- 直接运行识别会在量化 LSTM 处触发 `Illegal instruction`。服务器 CPU 仅暴露到 SSSE3，不支持 AVX2/FBGEMM；
- EasyOCR 默认 `quantize=True`，量化 LSTM 使用需要 AVX2 的 FBGEMM 内核；
- 改为 `quantize=False` 后，普通 LSTM 可运行；
- `NNPACK` 初始化警告仍会出现，但不影响识别结果。

验证证据：

| 检查 | 结果 |
|---|---|
| EasyOCR / torch / numpy 导入 | 正常 |
| Reader 初始化（`download_enabled=False, quantize=False`） | 成功，读取本地模型 |
| 文字图片 OCR（应用 `_ocr_image`） | 114 行文本；识别出“知产云档”“知识产权管理系统”“工作台”等 |
| PDF 渲染图 OCR | 51 行文本；识别出发票号码、开票日期、公司名称等 |
| 应用健康 | 正常 |
| 自动化测试 | `pytest -q` 176 passed |

未覆盖 / 说明：

- 已上传的无文字壁纸 JPG 重新识别后状态为 `failed / 未能从文件中提取到文字`，这是图片本身没有文字，不是崩溃；
- 模型下载依赖 GitHub，服务器直连速度很慢，本次使用本机已缓存的模型文件复制；
- 不要重新开启 `quantize=True`，也不要把 torch 升级到与当前 CPU 不兼容的版本。

## 四十三、材料文件类型展示与识别按钮限制（2026-11-16）

需求：上传时展示附件类型；上传后在材料列表展示类型；所有附件都可查看；只有 PDF 和图片显示识别入口。

实现：

- 文件类型由扩展名自动判断，不新增数据库字段：PDF、图片、Word、Excel、ZIP、其他；
- 上传抽屉选择文件后显示“类型”，列表新增“类型”列，查看弹窗和修改抽屉也显示类型；
- 只有 PDF 和图片渲染“识别”按钮；Word、Excel、ZIP 等隐藏按钮；
- 查看入口对所有类型保留；Office/ZIP 等不支持浏览器内预览的类型提示“请下载文件查看”，并保留下载按钮；
- 后端 `ensure_recognizable()` 同步校验，非 PDF/图片调用识别接口返回 422，避免只依赖前端隐藏。

验证证据：

| 检查 | 结果 |
|---|---|
| 自动化测试 | `pytest -q` **178 passed** |
| Vue SFC 编译 | 15 个组件通过，失败 0 |
| 前端生产构建 | JS 240.89 kB / gzip 78.29 kB，CSS 29.49 kB |
| 完整 deploy.sh 发布 | 成功部署 `20261116-180105`，健康检查正常 |
| 浏览器 CDP | **16 项检查全部通过**：PDF/图片/Word 类型展示正确；PDF/图片有识别按钮；Word 无识别按钮；三种类型均有查看按钮；Word 查看弹窗提示下载；上传抽屉选择 docx 后显示“Word” |
| 后端限制 | DOCX 调用 `POST /api/materials/{id}/extract` 返回 422 `该文件类型不支持识别，仅支持 PDF 和图片` |

说明：文件类型是派生展示，不是新的业务分类字段；现有“分类”（证书扫描件、申请文件等）保持不变。

## 四十四、登录 401 提示修正（2026-11-16）

问题：用户使用 `test` 账号登录时页面显示“登录已失效”，但服务端日志显示是登录请求返回 401。

日志证据：

```text
17:46:24 POST /api/auth/login 401
17:46:27 POST /api/auth/login 401
17:47:00 POST /api/auth/login 200
```

`test` 用户状态正常（active、未删除），17:47:00 的成功登录已创建有效会话。401 来自登录密码错误，但前端 `request()` 把所有 401 都映射成“登录已失效”，覆盖了服务端返回的“账号或密码错误”。

修复：

- `frontend/src/api.ts`：仅对非 `/auth/login` 请求的 401 做“会话失效”处理；登录接口的 401 继续解析服务端 detail；
- 部署版本：`20261116-180105`。

验证证据：

| 检查 | 结果 |
|---|---|
| 错误密码 | 页面显示“账号或密码错误”，不再显示“登录已失效” |
| 正确密码 | 成功进入工作台 |
| 自动化测试 | `pytest -q` 178 passed |
| 完整 deploy.sh | 发布成功，健康检查正常 |

说明：如果浏览器仍显示旧提示，先 `Ctrl + F5`；本次问题不是 `test` 账号被禁用或会话被撤销。

## 四十五、日期台账展示关联案件（2026-11-16）

需求：新建日期事项可以关联案件，日期台账列表需要展示该关联。

实现：

- `DateItemOut` 增加 `asset_name` 派生字段；
- 日期列表按当前页的 `ip_asset_id` 批量查询案件名称，不产生逐行查询；
- 日期台账新增「关联案件」列，点击案件名称跳转 `/assets/{id}`，未关联显示「未关联案件」；
- 已有新建抽屉的「关联案件」选择器保持不变。

验证证据：

| 检查 | 结果 |
|---|---|
| 自动化测试 | `pytest -q` **179 passed**（新增日期列表返回 `asset_name` 测试） |
| Vue SFC 编译 | 15 个组件通过，失败 0 |
| 生产 API | `/api/dates` 返回 `asset_name`，例如“基于图像的车辆重识别方法、装置、服务器及存储介质” |
| 浏览器 CDP | 登录 → 日期台账，确认「关联案件」列和案件名称正常显示 |
| 完整 deploy.sh | 成功部署 `20261116-180105`，健康检查正常 |

未覆盖 / 说明：

- 未单独测试“未关联案件”行在真实数据中的显示；代码分支已实现，空值显示「未关联案件」。
