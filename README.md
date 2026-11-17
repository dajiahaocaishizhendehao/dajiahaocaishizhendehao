# 知识产权管理系统（专利 / 软著 / 商标）

按 `docs/PRODUCT_SPEC.md` 与 `prototype/` 原型实现的知识产权档案系统。

## 一句话状态

**系统可运行、可测试、已部署**：后端 62 个接口通过静态审计（均有鉴权、无重复路由），前端 15 个 Vue 组件完成 SFC 编译与生产构建。后端已在真实 uvicorn 上跑通 **32 项端到端检查**（2026-11-11 最近一次执行）；SQLite 迁移已完整验证到 `0010_copyright_certificate_date`。2026-11-16 已在 openEuler 22.03 + PostgreSQL 13.23 上完成真实部署：迁移到 `0010`、服务与 Nginx 启动、浏览器登录工作台、204 退出接口均验证通过。

| 项 | 状态 |
|---|---|
| 前端构建 / 类型检查 / 浏览器渲染 / 登录交互 | 已验证 |
| 后端接口 / 权限 / 审计 / 导入导出 | 已验证（32 项端到端，2026-11-11） |
| 数据库迁移（SQLite） | 已验证：升级到 `0010_copyright_certificate_date`，含 0010 升级 / 降级 / 再升级 |
| 数据库迁移与运行（PostgreSQL 13.23） | 已验证：openEuler 生产部署，Alembic `0010`，服务与登录正常 |
| 自动备份 | 已验证：每日 02:00 systemd timer，保留 14 天，已完成临时库恢复演练 |
| 生产环境 PDF 预览 / 文本识别 | 已验证：PyMuPDF 2.1，文字层 PDF 可预览并提取字段 |
| 生产环境图片 OCR | 已验证：EasyOCR 1.7.2，`quantize=False`，中文文字图片识别成功 |
| 生产环境 Excel 导入导出 / 文件恢复 | **未验证** |
| pytest | 已验证（`179 passed`） |

- 后端：FastAPI + SQLAlchemy 2 + Alembic + PostgreSQL
- 前端：Vue 3 + TypeScript + Vite
- 文件：本地目录存储（可替换为对象存储）
- 原型：`prototype/` 下的纯静态可点击原型，保留作为设计对照

## 目录结构

```text
backend/     FastAPI 服务、数据模型、迁移与测试
frontend/    Vue 3 + TypeScript 前端
prototype/   静态交互原型（设计对照，不参与构建）
docs/        产品规格、决策与待确认问题
AGENTS.md    开发代理规则
```

## 一、准备环境

需要：

- Python 3.12（最低 3.10；当前只在 3.12 上测试）
- Node.js 20+ 与 pnpm
- PostgreSQL 14+

### 1. 数据库

创建库与账号（示例值，请自行替换）：

```sql
CREATE USER ipms WITH PASSWORD 'ipms';
CREATE DATABASE ipms OWNER ipms;
```

### 2. 后端

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

copy .env.example .env      # Windows
# cp .env.example .env      # macOS/Linux

alembic upgrade head
python -m tools.create_admin --username admin --password 'ChangeMe!123' --name 管理员
uvicorn app.main:app --reload --port 8000
```

接口文档：http://127.0.0.1:8000/docs

### 3. 前端

```bash
cd frontend
pnpm install
pnpm dev
```

打开 http://localhost:5173 ，使用上一步创建的管理员账号登录。

## 二、已实现的接口

| 模块 | 主要接口 |
|---|---|
| 认证 | `POST /api/auth/login`、`POST /api/auth/logout`、`GET /api/auth/me` |
| 档案 | `GET/POST /api/assets`、`GET/PATCH/DELETE /api/assets/{id}` |
| 历史证书兼容接口 | `GET/POST /api/certificates`、`PATCH /api/certificates/{id}`（前端页面已下线，暂保留数据兼容） |
| 材料 | `GET/POST /api/materials`、`PATCH/DELETE /api/materials/{id}`、`POST /api/materials/{id}/replace`、`GET /api/materials/{id}/download`、`GET /api/materials/{id}/preview`、`POST /api/materials/{id}/extract` |
| 日期 | `GET/POST /api/dates`、`PATCH /api/dates/{id}`、`POST /api/dates/{id}/complete` |
| 费用 | `GET/POST /api/fees`、`GET/PATCH/DELETE /api/fees/{id}` |
| 发票 | `GET/POST /api/invoices`、`PATCH /api/invoices/{id}`、`POST /api/invoices/recognize`、费用与发票关联接口 |
| 基础资料 | `GET/POST/PATCH/DELETE /api/parties`、`GET/POST/PATCH/DELETE /api/agencies`、`GET/POST/PATCH/DELETE /api/projects`、`/api/persons`（仅档案发明人/设计人关联） |
| 统计 | `GET /api/stats/dashboard`、`GET /api/stats/workbench`、`GET /api/stats/yearly` |
| 用户与审计 | `GET/POST /api/users`（`q` 支持姓名 / 账号搜索）、`PATCH/DELETE /api/users/{id}`、`GET /api/audit-logs` |
| 导入导出 | `GET /api/export/assets.csv`、`GET /api/export/assets.xlsx`、`GET /api/import/assets/template.xlsx`、`POST /api/import/assets` |

## 二·五、前端页面

| 路由 | 页面 |
|---|---|
| `/login` | 登录 |
| `/` | 工作台（待办、对账、材料处理、全局搜索、CSV 档案导入） |
| `/assets` | 全部知识产权（检索、筛选、新建；默认未取得在前、已取得按授权公告日倒序） |
| `/assets/:id` | 档案详情 |
| `/trademarks` | 商标 / Logo |
| `/materials` | 材料中心（申请材料、证书扫描件、上传资料弹窗、修改备注 / 更换文件、在线查看、识别、下载、删除） |
| `/dates` | 日期台账（标记完成） |
| `/fees` | 费用台账（费用详情内登记、查看发票） |
| `/fees/:id` | 费用详情与关联发票 |
| `/users` | 系统管理（用户搜索、新建、编辑、删除，操作日志） |
| `/meta` | 基础资料（权利人、代理机构、项目 / 产品） |

## 三、关键业务约定

- 专利、软著、商标共用 `ip_assets` 主档，专业字段分别存于 `patents`、`copyrights`、`trademarks`。
- 档案以**案件名称**为主展示，`docket_no`（我方文号）用于按内部文号检索与对账。
- 全部知识产权列表展示「授权公告日」：专利取 `patents.grant_date`，软著取 `copyrights.certificate_date`，商标显示 `—`；默认排序为未取得权利在前，已取得按授权公告日倒序，已取得但无日期的排在其后，组内按更新时间倒序。专利与软著均可在新建 / 编辑表单中维护该日期。
- 不再设置独立的“已取得权利 / 证书”页面；证书扫描件作为电子材料，在材料中心按案件管理和识别。
- 系统不管理证书纸质原件的领取、借出或移交流程。
- 材料、费用、发票、日期均按案件名称关联与筛选。材料中心上传分类中「证书扫描件」位于下拉第一位并默认选中；分类枚举与后端字段不变。
- 材料中心上传材料时可填写备注（可选，最多 500 字），备注在材料列表「备注」列与查看弹窗中展示，无备注显示 `—`；备注保存于既有 `materials.remark` 字段，未新增数据库列。
- 材料中心页面只保留一个「上传资料」按钮；点击后在右侧抽屉中填写关联案件、分类、文件与备注，文件使用「选择文件」按钮选取并显示文件名 / 大小，可清除。`/materials?upload=1` 直接打开该抽屉，带 `asset` 参数时预选案件。
- 材料类型按文件扩展名自动判断并在上传抽屉、列表和查看弹窗展示：PDF、图片、Word、Excel、ZIP、其他，不新增数据库字段。只有 PDF 和图片显示「识别」按钮，后端对其他类型返回 422；所有类型都保留「查看」入口，Office / ZIP 等不支持浏览器内预览的类型提示下载后查看。
- 各列表页的操作按钮统一放在页面标题下方、数据表（或卡片列表）上方的工具栏中，主操作在最左：材料中心为「上传资料 → 搜索 → 查询」，工作台为「搜索框 → 新建案件 → 上传材料 → 导入档案 → 登记费用」，其余页面为「新建 / 登记 → 搜索 / 筛选」，页头不再放按钮。工作台搜索框固定 420px 宽，位于「新建案件」左侧；搜索结果右侧为不换行的「查看案件」胶囊按钮，超长案件名称单行省略。
- 材料中心行操作「修改」（仅可写角色）可修改备注，或选择新文件更换；更换时旧文件按确认的保留策略留在存储层（数据库只指向新文件），审计记录 `replace_file` 及新旧对象键 / 哈希，识别结果同时重置。仅当显示名称仍等于旧原始文件名时才会跟随新文件名。
- CSV / XLSX 档案导入集成在工作台弹窗中，不再提供独立数据导入页面；模板列为 `我方文号,申请号,案件名称,专利所有权人,官费应缴纳日,本次官费缴纳至,本次官费缴纳金额,缴纳日期`，只有「案件名称」必填，XLSX 读取第一个工作表。
- 年费记录区分三个日期：官费应缴日（`due_date`）、实缴日（`paid_date`）、本次缴费缴至（`coverage_end_date`）。
- **证书识别只产出建议值，必须人工确认后才写入档案**（对应 AGENTS.md 对 OCR 的要求）。识别使用本机 EasyOCR（中文模型已缓存），不联网。
- 一张档案只能提交与自身类型匹配的专业字段，否则返回 422。
- 内部档案编号已按 D-018 彻底取消：新建、详情、列表、导入导出均不再出现该字段，数据库也不保留该列；案件以名称和我方文号检索。
- 删除为逻辑删除，详情与列表不再返回，审计记录保留。
- 金额使用 `Numeric(14,2)` 并保存币种；应付、实付、发票金额互不推算。
- 证书相关文件作为材料保存；历史证书后端表/API 暂时保留，仅用于兼容已有数据，不设前端入口。
- 日期由用户录入，系统不推导法律期限；`/api/stats/dashboard` 会一并返回每个指标的统计口径。
- 日期事项可关联知识产权案件；日期台账列表展示「关联案件」列，点击可进入档案详情，未关联时显示「未关联案件」。
- 角色只有三种：`admin`（系统管理员）、`ip_admin`（管理员）可写；`user`（普通用户）只读。所有登录用户可查看全部档案。历史账号由迁移 `0008_merge_user_roles` 把原 `dept_user`、`viewer` 合并为 `user`。
- 退出登录只撤销当前浏览器的会话，其他设备上的登录保持有效；会话默认有效期 720 分钟。
- 系统已取消部门字段和部门表，基础资料与系统管理都不再显示部门；历史数据库由迁移 `0007_drop_departments` 清理。
- 基础资料只维护权利人、代理机构、项目 / 产品；人员即系统用户，搜索、新建、编辑、删除统一在系统管理 → 用户完成。原 `persons` 表只保留给档案的发明人 / 设计人关联；档案详情页的「关联人员」抽屉可选用现有 `persons` 记录，也可现场按「姓名 + 人员类型」新建后直接关联，不提供独立人员档案页面。
- 权利人、代理机构、项目 / 产品支持新建、编辑、逻辑删除；删除不会物理清除关联历史数据。
- 材料识别结果只作为建议值，可在确认弹窗中手工修改；修改后立即重算「新增 / 将覆盖 / 一致 / 未识别」并自动勾选。点「写入档案」成功后按钮变为「已写入」并置灰；之后若再改出「新增 / 将覆盖」内容，按钮恢复可点击，可再次提交这次修改。
- 档案详情页「专利信息 / 软著信息 / 商标信息」板块右上角提供「编辑」，跳转到 `/assets?edit=<id>` 并自动打开编辑抽屉；「权利人与人员」板块提供「关联人员」，可取消关联、从现有人员中选择或现场新建，保存时整组替换该档案的人员关联。两个入口仅对可写角色显示，服务端仍按原有权限校验。
- 专利详情页只展示专利类型、申请号、申请日期、公开号、公开日期、专利号、授权公告日、法律状态；申请国家 / 地区、代理机构、代理师、技术领域、摘要、专利权期限届满日仍保存在数据库和 API 中，但不在详情页展示。
- 全部知识产权的新建 / 编辑抽屉可维护公开号、公开日期、授权公告日、法律状态；法律状态目前是自由文本（后端字段 `String(64)`），未定义枚举或数据字典。
- 新建档案时「知识产权类型」排在我方文号之前；选择软件著作权时隐藏我方文号，表单改为录入软件名称（存入 `ip_assets.name`）、著作权人、权利取得方式（下拉：原始取得 / 继受取得 / 其他）与授权公告日。著作权人按名称 + 类型新建 `parties` 记录并关联；授权公告日对应 `copyrights.certificate_date`（迁移 `0010`），接口字段名保持 `certificate_date`。软著编辑抽屉同样回填并修改著作权人、权利取得方式与授权公告日；修改著作权人名称会更新原权利人记录（其他引用该权利人的档案同步变化），部分更新不会清空权利人的其他字段。软著详情页也以「授权公告日」展示该日期。
- 软著详情页的「软著信息」板块展示「著作权人」「著作权人类型」「权利取得方式」「授权公告日」「备注」五项，与新建 / 编辑抽屉的可维护项一致；著作权人取该档案第一个关联权利人（其余权利人仍在「权利人与人员」板块列出），备注不再在基本信息板块重复展示。版本号、软件分类、软件简称、登记号 / 登记日期、申请 / 受理日期、证书编号、开发完成日期、首次发表信息、开发语言、运行平台、开发方式、软件用途、技术特点仍保存在数据库和 API 中，但暂不在详情页展示。

## 四、测试与自检

接口清单见 [docs/API.md](docs/API.md)；已执行与未执行的验证项目见 [docs/VERIFICATION.md](docs/VERIFICATION.md)。

```bash
# 不依赖任何第三方库的自检（语法、导入、前端结构、接口审计、业务规则单测）
python scripts/verify.py --offline

# 若有装了 pydantic / fastapi 的解释器，可额外运行模型与 HTTP 契约测试
IPMS_SCHEMA_PYTHON=<python 路径> python scripts/verify.py --offline

# 安装依赖后：自检 + pytest + 前端类型检查
python scripts/verify.py

# 仅安全模块（密码哈希、令牌、角色与数据范围），零依赖
python scripts/smoke_security.py

# 仅接口静态审计（重复路由、缺失鉴权、未注册模块）
python scripts/api_audit.py

# 仅前后端字段契约检查
python scripts/contract_check.py

# 仅 ORM 模型检查（外键目标、属性拼写）
python scripts/model_check.py

# 仅纯业务规则单测（也可被 pytest 收集）
python -m unittest discover -s backend/tests -t backend -p "test_domain.py"
```

后端测试：

```bash
cd backend
pytest -q
```

测试默认使用内存 SQLite，不需要本地 PostgreSQL。

## 五、当前进度与未验证项

**系统已经可以真实运行**：`scripts/live_api_check.py` 会启动真实 uvicorn（临时 SQLite 库），跑完 **32 项 HTTP 检查**，覆盖登录、档案增删改查、类型隔离、日期、费用、发票、材料上传下载、统计、CSV 导入导出、权限、审计与逻辑删除。2026-11-11 最近一次执行全部通过。

已完成并实际验证：

- **端到端**：真实 uvicorn + SQLite，32 项检查全通过（含越权与审计）；
- **数据库**：全新 SQLite 可从零迁移到 `0010_copyright_certificate_date`，建立 19 张业务表；历史库升级、0010 降级与再升级均实测通过；
- **前端**：15 个 Vue 组件完成 SFC/TypeScript 检查；`vite build` 可产出 `dist`（JS 240.89 kB / gzip 78.29 kB，CSS 29.49 kB）；
- **浏览器**：无头 Edge 加载产物，工作台 / 材料 / 日期页面带着真实令牌调用真实接口并渲染成功，匿名访问被路由守卫挡回登录页；
- **浏览器交互**：通过 CDP 真实填入账号密码、点击登录、跳转工作台并刷新保持登录态（10 项检查通过）；
- **详情页编辑与人员关联**：通过 CDP 实际点击「编辑」跳转编辑抽屉并保存成功；「关联人员」抽屉中现场新建人员、保存关联、取消关联均与后端一致（25 项检查通过）；
- **生产部署**：openEuler 22.03 + PostgreSQL 13.23，Alembic 从基线迁移到 `0010`，建立 19 张业务表；systemd（运行用户 `ipms`）、Nginx、firewalld 正常，站点首页 200；浏览器 CDP 登录工作台 8 项检查全部通过，204 退出接口响应体为空；
- **自动备份**：`ipms-backup.timer` 每天 02:00 备份 PostgreSQL 与上传目录并保留 14 天；已把备份恢复至临时库验证（20 张 public 表、`0010`、1 个用户）；
- **PDF 预览与识别**：安装 PyMuPDF 2.1，文字层 PDF 预览返回 200（1 页），识别状态 `succeeded`，可提取名称、申请日、授权日等建议字段；
- **图片 OCR**：安装 EasyOCR 1.7.2 + CPU 版 PyTorch，模型缓存于服务器；关闭量化 LSTM（`quantize=False`）以兼容无 AVX2 的 CPU，中文文字图片识别成功；
- **测试**：`pytest -q` 179 项全部通过；纯业务规则与查询测试 47 项、契约层测试 43 项全部通过；
- **静态检查**：导入解析、ORM 模型检查（21 模型 / 19 表）、62 个接口审计、前后端字段契约、前端路由目标。

未验证：

- **生产环境材料上传 / 下载、Excel 导入导出、文件恢复**尚未在 PostgreSQL 服务器上逐项执行；
- **浏览器内点击验证内部编号移除**（已由 SFC 编译、生产构建、接口响应与端到端检查覆盖，但未做浏览器实际点击）。

真实运行中发现并修复的缺陷：

1. 借出/归还日期校验从未生效（`info.data` 用法错误）；
2. 受限角色未分配部门时被放大为全量访问（越权）。该问题随 D-014 取消部门范围而失效：现在所有登录用户本就可看全部档案；
3. 生产部署时发现 `fastapi==0.115.6` 会把 204 路由的 `-> None` 推断为响应模型并在启动时断言失败；已将依赖固定为 `0.115.14`，并为 8 个 204 路由显式设置 `response_model=None`；
4. 安装 PyMuPDF 时被带入 NumPy 2.5.5，其 X86_V2 基线不被服务器 CPU 支持，导致 Excel 导入接口在 `import openpyxl` 时 500；已固定 `numpy==1.26.4`；
5. 服务器 CPU 不支持 AVX2/FBGEMM，EasyOCR 默认的量化 LSTM 会触发 `Illegal instruction`；已改用 CPU 版 PyTorch，并在 Reader 中设置 `quantize=False`。

说明：本地开发环境没有 PostgreSQL；真实 PostgreSQL 验证在 openEuler 服务器上完成，范围见 [docs/VERIFICATION.md](docs/VERIFICATION.md) 第三十四节。

## 六、部署

openEuler 22.03 + PostgreSQL + 内网访问的打包、systemd、Nginx、SELinux、备份与升级步骤见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)。本机也可用 `bash scripts/deploy.sh` 一键发布，`bash scripts/rollback.sh --list` 查看版本。

## 七、已知限制

- `backend/alembic/versions/0001_initial.py` 以 ORM 元数据创建基线表；后续结构调整必须改为显式迁移语句。
- 部门字段已取消，角色权限矩阵仍待确认（`docs/OPEN_QUESTIONS.md` Q-003）。
- 商标分类体系、法域与续展规则未确认（Q-011、Q-012）。
- 导入支持 CSV / XLSX 的八列模板；其他历史台账列定义仍待确认（Q-009）。
- 内部编号字段已按 D-018 彻底删除，历史编号不可恢复；旧导入模板中的 `asset_no` 列会被忽略。
- 独立证书/原件前端页面已下线；历史后端证书结构暂保留用于数据兼容。
