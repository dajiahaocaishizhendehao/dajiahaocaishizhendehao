# 接口清单

> 本文件由 `python scripts/gen_api_doc.py` 从路由声明静态生成，请勿手工编辑。
> 生成日期：2026-11-12；接口总数：62。

运行时完整 OpenAPI（含请求体字段）请访问 `http://127.0.0.1:8000/docs`。

## 系统管理

| 方法 | 路径 | 响应模型 | 权限 |
|---|---|---|---|
| `GET` | `/api/users` | `Page[UserOut]` | 需管理员 |
| `POST` | `/api/users` | `UserOut` | 需管理员 |
| `PATCH` | `/api/users/{user_id}` | `UserOut` | 需管理员 |
| `DELETE` | `/api/users/{user_id}` | `—` | 需管理员 |
| `GET` | `/api/audit-logs` | `Page[AuditLogOut]` | 需管理员 |
| `GET` | `/api/export/assets.csv` | `—` | 登录即可 |
| `GET` | `/api/export/assets.xlsx` | `—` | 登录即可 |
| `GET` | `/api/import/assets/template.xlsx` | `—` | 需写权限（admin / ip_admin） |
| `POST` | `/api/import/assets` | `ImportResult` | 需写权限（admin / ip_admin） |

## 知识产权档案

| 方法 | 路径 | 响应模型 | 权限 |
|---|---|---|---|
| `GET` | `/api/assets` | `Page[AssetListItem]` | 登录即可 |
| `GET` | `/api/assets/{asset_id}` | `AssetDetail` | 登录即可 |
| `POST` | `/api/assets` | `AssetDetail` | 需写权限（admin / ip_admin） |
| `PATCH` | `/api/assets/{asset_id}` | `AssetDetail` | 需写权限（admin / ip_admin） |
| `DELETE` | `/api/assets/{asset_id}` | `—` | 需写权限（admin / ip_admin） |

## 认证

| 方法 | 路径 | 响应模型 | 权限 |
|---|---|---|---|
| `POST` | `/api/auth/login` | `TokenOut` | 无（公开） |
| `POST` | `/api/auth/logout` | `—` | 登录即可 |
| `GET` | `/api/auth/me` | `UserOut` | 登录即可 |

## 证书

| 方法 | 路径 | 响应模型 | 权限 |
|---|---|---|---|
| `GET` | `/api/certificates` | `Page[CertificateOut]` | 登录即可 |
| `POST` | `/api/certificates` | `CertificateOut` | 需写权限（admin / ip_admin） |
| `PATCH` | `/api/certificates/{certificate_id}` | `CertificateOut` | 需写权限（admin / ip_admin） |

## 日期与提醒

| 方法 | 路径 | 响应模型 | 权限 |
|---|---|---|---|
| `GET` | `/api/dates` | `Page[DateItemOut]` | 登录即可 |
| `POST` | `/api/dates` | `DateItemOut` | 需写权限（admin / ip_admin） |
| `PATCH` | `/api/dates/{item_id}` | `DateItemOut` | 需写权限（admin / ip_admin） |
| `POST` | `/api/dates/{item_id}/complete` | `DateItemOut` | 需写权限（admin / ip_admin） |

## 费用与发票

| 方法 | 路径 | 响应模型 | 权限 |
|---|---|---|---|
| `GET` | `/api/fees` | `Page[FeeOut]` | 登录即可 |
| `POST` | `/api/fees` | `FeeOut` | 需写权限（admin / ip_admin） |
| `PATCH` | `/api/fees/{fee_id}` | `FeeOut` | 需写权限（admin / ip_admin） |
| `DELETE` | `/api/fees/{fee_id}` | `—` | 需写权限（admin / ip_admin） |
| `POST` | `/api/invoices/recognize` | `—` | 需写权限（admin / ip_admin） |
| `GET` | `/api/fees/{fee_id}` | `FeeOut` | 登录即可 |
| `GET` | `/api/fees/{fee_id}/invoices` | `Page[InvoiceOut]` | 登录即可 |
| `POST` | `/api/fees/{fee_id}/invoices/{invoice_id}` | `—` | 需写权限（admin / ip_admin） |
| `GET` | `/api/invoices` | `Page[InvoiceOut]` | 登录即可 |
| `POST` | `/api/invoices` | `InvoiceOut` | 需写权限（admin / ip_admin） |
| `PATCH` | `/api/invoices/{invoice_id}` | `InvoiceOut` | 需写权限（admin / ip_admin） |

## 电子材料

| 方法 | 路径 | 响应模型 | 权限 |
|---|---|---|---|
| `GET` | `/api/materials` | `Page[MaterialOut]` | 登录即可 |
| `POST` | `/api/materials` | `MaterialOut` | 需写权限（admin / ip_admin） |
| `PATCH` | `/api/materials/{material_id}` | `MaterialOut` | 需写权限（admin / ip_admin） |
| `POST` | `/api/materials/{material_id}/replace` | `MaterialOut` | 需写权限（admin / ip_admin） |
| `DELETE` | `/api/materials/{material_id}` | `—` | 需写权限（admin / ip_admin） |
| `GET` | `/api/materials/{material_id}/preview` | `—` | 登录即可 |
| `POST` | `/api/materials/{material_id}/extract` | `—` | 需写权限（admin / ip_admin） |
| `POST` | `/api/materials/{material_id}/extract-invoice` | `—` | 需写权限（admin / ip_admin） |
| `GET` | `/api/materials/{material_id}/extraction` | `—` | 登录即可 |
| `GET` | `/api/materials/{material_id}/download` | `—` | 登录即可 |

## 基础资料

| 方法 | 路径 | 响应模型 | 权限 |
|---|---|---|---|
| `GET` | `/api/agencies` | `Page[AgencyOut]` | 登录即可 |
| `POST` | `/api/agencies` | `AgencyOut` | 需写权限（admin / ip_admin） |
| `GET` | `/api/projects` | `Page[ProjectOut]` | 登录即可 |
| `POST` | `/api/projects` | `ProjectOut` | 需写权限（admin / ip_admin） |
| `GET` | `/api/parties` | `Page[PartyOut]` | 登录即可 |
| `POST` | `/api/parties` | `PartyOut` | 需写权限（admin / ip_admin） |
| `PATCH` | `/api/parties/{party_id}` | `PartyOut` | 需写权限（admin / ip_admin） |
| `DELETE` | `/api/parties/{party_id}` | `—` | 需写权限（admin / ip_admin） |
| `PATCH` | `/api/agencies/{agency_id}` | `AgencyOut` | 需写权限（admin / ip_admin） |
| `DELETE` | `/api/agencies/{agency_id}` | `—` | 需写权限（admin / ip_admin） |
| `PATCH` | `/api/projects/{project_id}` | `ProjectOut` | 需写权限（admin / ip_admin） |
| `DELETE` | `/api/projects/{project_id}` | `—` | 需写权限（admin / ip_admin） |
| `GET` | `/api/persons` | `Page[PersonOut]` | 登录即可 |
| `POST` | `/api/persons` | `PersonOut` | 需写权限（admin / ip_admin） |

## 统计

| 方法 | 路径 | 响应模型 | 权限 |
|---|---|---|---|
| `GET` | `/api/stats/workbench` | `WorkbenchOut` | 登录即可 |
| `GET` | `/api/stats/dashboard` | `DashboardOut` | 登录即可 |
| `GET` | `/api/stats/yearly` | `YearlyOut` | 登录即可 |

## 约定

- 所有接口前缀为 `/api`；`/health` 为健康检查。
- 列表接口统一返回 `{items, total, page, page_size}`。
- 删除为逻辑删除，返回 `204`。
- 金额使用定点小数，接口中为字符串形式的十进制数。
- 日期为 `YYYY-MM-DD`，时间为带时区 ISO 8601。
