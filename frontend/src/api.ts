/** 统一 API 客户端：负责令牌注入、错误归一化与 JSON 解析。 */

import { formatValidationMessage } from './labels'

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface User {
  id: string
  username: string
  display_name: string
  role: 'admin' | 'ip_admin' | 'user'
  email: string | null
  phone: string | null
  is_active: boolean
}

export interface AssetListItem {
  id: string
  name: string
  docket_no?: string | null
  ip_type: 'patent' | 'copyright' | 'trademark'
  status_group: 'in_progress' | 'granted' | 'invalid' | 'other'
  owner_user_id: string | null
  grant_date?: string | null
  updated_at: string
}

export interface AssetDetail extends AssetListItem {
  project_id: string | null
  remark: string | null
  created_at: string
  patent: Record<string, unknown> | null
  copyright: Record<string, unknown> | null
  trademark: Record<string, unknown> | null
  parties: Array<{ id: string; name: string; party_type: string }>
  persons: Array<{ id: string; name: string; person_type: string }>
}

export interface DateItem {
  id: string
  ip_asset_id: string | null
  asset_name?: string | null
  title: string
  date_type: string
  planned_date: string | null
  due_date: string | null
  actual_date: string | null
  remark?: string | null
  status: string
  source: string
  needs_confirmation: boolean
}

export interface MetricDefinition {
  key: string
  label: string
  source: string
  filter: string
  date_field: string | null
  dedup: string
  status_scope: string | null
  empty_behavior: string
}

export interface Dashboard {
  total_assets: number
  by_type: Record<string, number>
  by_status: Record<string, number>
  granted_rate: number
  new_this_year: number
  certificates_by_type: Record<string, number>
  due_soon: DateItem[]
  due_soon_days: number
  metrics: MetricDefinition[]
}

export interface WorkbenchTask {
  id: string
  ip_asset_id: string | null
  asset_name: string | null
  title: string
  date_type: string
  due_date: string
  days_left: number
}

export interface WorkbenchFee {
  id: string
  ip_asset_id: string
  asset_name: string
  docket_no: string | null
  fee_type: string
  amount_paid: string | null
  amount_due: string
  currency: string
  paid_date: string | null
}

export interface WorkbenchMaterial {
  id: string
  ip_asset_id: string | null
  asset_name: string | null
  display_name: string
  extraction_status: 'pending' | 'running' | 'failed'
  extraction_kind: string | null
  extraction_error: string | null
  updated_at: string
}

export interface Workbench {
  total_assets: number
  in_progress_assets: number
  pending_date_count: number
  missing_invoice_fee_count: number
  extraction_attention_count: number
  tasks: WorkbenchTask[]
  missing_invoice_fees: WorkbenchFee[]
  extraction_attention: WorkbenchMaterial[]
  recent_assets: AssetListItem[]
  due_soon_days: number
  metrics: MetricDefinition[]
}

export interface YearlyStat {
  date_field: string
  ip_type: string | null
  items: Array<{ year: number; count: number }>
  metric: MetricDefinition
}

const TOKEN_KEY = 'ipms_token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

export class ApiError extends Error {
  status: number
  code?: string
  fields?: Record<string, { type: string; msg: string }>
  constructor(
    status: number,
    message: string,
    code?: string,
    fields?: Record<string, { type: string; msg: string }>,
  ) {
    super(message)
    this.status = status
    this.code = code
    this.fields = fields
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')

  const response = await fetch(`/api${path}`, { ...init, headers })
  // 登录接口的 401 表示账号或密码错误；只有已登录请求的 401 才是会话失效。
  if (response.status === 401 && path !== '/auth/login') {
    setToken(null)
    if (!location.hash.includes('/login')) location.hash = '#/login'
    throw new ApiError(401, '登录已失效')
  }
  if (!response.ok) {
    let detail = `请求失败（${response.status}）`
    let code: string | undefined
    let fields: Record<string, { type: string; msg: string }> | undefined
    try {
      const body = await response.json()
      if (body?.code === 'validation_error' && body.fields) {
        code = body.code
        fields = body.fields
        detail = formatValidationMessage(body.fields)
      } else if (typeof body.detail === 'string') {
        detail = body.detail
        if (typeof body.code === 'string') code = body.code
      } else if (Array.isArray(body.detail) && body.detail[0]?.msg) {
        detail = body.detail[0].msg
      }
    } catch {
      /* 保持默认提示 */
    }
    throw new ApiError(response.status, detail, code, fields)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

async function downloadAuthorized(path: string, filename: string): Promise<void> {
  const token = getToken()
  const response = await fetch(`/api${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
  if (response.status === 401) {
    setToken(null)
    location.hash = '#/login'
    throw new ApiError(401, '登录已失效')
  }
  if (!response.ok) throw new ApiError(response.status, `下载失败（${response.status}）`)
  const url = URL.createObjectURL(await response.blob())
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = filename; anchor.click()
  setTimeout(() => URL.revokeObjectURL(url), 0)
}

function toQuery(params: Record<string, unknown>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

/** 获取材料预览图；PDF 可指定页码，响应头 X-Page-Count 给出总页数。 */
async function fetchPreviewPage(id: string, page: number): Promise<{ url: string; pageCount: number }> {
  const token = getToken()
  const response = await fetch(`/api/materials/${id}/preview?page=${page}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!response.ok) {
    let detail = `预览失败（${response.status}）`
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      /* 保持默认提示 */
    }
    throw new ApiError(response.status, detail)
  }
  const pageCount = Math.max(1, Number(response.headers.get('X-Page-Count') ?? '1') || 1)
  return { url: URL.createObjectURL(await response.blob()), pageCount }
}

export const api = {
  login: (username: string, password: string) =>
    request<{ access_token: string; user: User }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  logout: () => request<void>('/auth/logout', { method: 'POST' }),
  me: () => request<User>('/auth/me'),

  workbench: (days?: number) => request<Workbench>(`/stats/workbench${toQuery({ due_soon_days: days })}`),
  dashboard: (days?: number) => request<Dashboard>(`/stats/dashboard${toQuery({ due_soon_days: days })}`),
  yearly: (params: Record<string, unknown> = {}) => request<YearlyStat>(`/stats/yearly${toQuery(params)}`),

  assets: (params: Record<string, unknown>) => request<Page<AssetListItem>>(`/assets${toQuery(params)}`),
  asset: (id: string) => request<AssetDetail>(`/assets/${id}`),
  createAsset: (payload: unknown) =>
    request<AssetDetail>('/assets', { method: 'POST', body: JSON.stringify(payload) }),
  updateAsset: (id: string, payload: unknown) =>
    request<AssetDetail>(`/assets/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteAsset: (id: string) => request<void>(`/assets/${id}`, { method: 'DELETE' }),

  materials: (params: Record<string, unknown>) => request<Page<Record<string, unknown>>>(`/materials${toQuery(params)}`),
  uploadMaterial: (form: FormData) => request<Record<string, unknown>>('/materials', { method: 'POST', body: form }),
  updateMaterial: (id: string, payload: unknown) =>
    request<Record<string, unknown>>(`/materials/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  replaceMaterialFile: (id: string, form: FormData) =>
    request<Record<string, unknown>>(`/materials/${id}/replace`, { method: 'POST', body: form }),
  deleteMaterial: (id: string) => request<void>(`/materials/${id}`, { method: 'DELETE' }),
  extractMaterial: (id: string) =>
    request<{
      material_id: string
      status: string
      source: string | null
      text: string
      fields: Record<string, string>
      warnings: string[]
      needs_review: boolean
    }>(`/materials/${id}/extract`, { method: 'POST' }),
  retryInvoiceExtraction: (id: string) =>
    request<{ material_id: string; status: string }>(`/materials/${id}/extract-invoice`, { method: 'POST' }),
  extractionResult: (id: string) =>
    request<{
      material_id: string
      status: 'none' | 'pending' | 'running' | 'succeeded' | 'failed'
      source: string | null
      text: string
      fields: Record<string, string>
      warnings: string[]
      error: string | null
      needs_review: boolean
    }>(`/materials/${id}/extraction`),
  async previewMaterialUrl(id: string): Promise<string> {
    const { url } = await fetchPreviewPage(id, 0)
    return url
  },
  previewMaterialPage: (id: string, page = 0) => fetchPreviewPage(id, page),
  createParty: (payload: unknown) =>
    request<{ id: string; name: string }>('/parties', { method: 'POST', body: JSON.stringify(payload) }),
  updateParty: (id: string, payload: unknown) =>
    request<Record<string, unknown>>(`/parties/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteParty: (id: string) => request<void>(`/parties/${id}`, { method: 'DELETE' }),
  createAgency: (payload: unknown) =>
    request<Record<string, unknown>>('/agencies', { method: 'POST', body: JSON.stringify(payload) }),
  updateAgency: (id: string, payload: unknown) =>
    request<Record<string, unknown>>(`/agencies/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteAgency: (id: string) => request<void>(`/agencies/${id}`, { method: 'DELETE' }),
  createProject: (payload: unknown) =>
    request<Record<string, unknown>>('/projects', { method: 'POST', body: JSON.stringify(payload) }),
  updateProject: (id: string, payload: unknown) =>
    request<Record<string, unknown>>(`/projects/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteProject: (id: string) => request<void>(`/projects/${id}`, { method: 'DELETE' }),

  dates: (params: Record<string, unknown>) => request<Page<DateItem>>(`/dates${toQuery(params)}`),
  createDate: (payload: unknown) => request<DateItem>('/dates', { method: 'POST', body: JSON.stringify(payload) }),
  updateDate: (id: string, payload: unknown) =>
    request<DateItem>(`/dates/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  completeDate: (id: string) => request<DateItem>(`/dates/${id}/complete`, { method: 'POST' }),

  fees: (params: Record<string, unknown>) => request<Page<Record<string, unknown>>>(`/fees${toQuery(params)}`),
  createFee: (payload: unknown) => request<Record<string, unknown>>('/fees', { method: 'POST', body: JSON.stringify(payload) }),
  updateFee: (id: string, payload: unknown) =>
    request<Record<string, unknown>>(`/fees/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteFee: (id: string) => request<void>(`/fees/${id}`, { method: 'DELETE' }),
  fee: (id: string) => request<Record<string, unknown>>(`/fees/${id}`),
  feeInvoices: (feeId: string) =>
    request<Page<Record<string, unknown>>>(`/fees/${feeId}/invoices?page=1&page_size=50`),
  linkFeeInvoice: (feeId: string, invoiceId: string) =>
    request<Record<string, unknown>>(`/fees/${feeId}/invoices/${invoiceId}`, { method: 'POST' }),

  invoices: (params: Record<string, unknown>) =>
    request<Page<Record<string, unknown>>>(`/invoices${toQuery(params)}`),
  createInvoice: (payload: unknown) =>
    request<Record<string, unknown>>('/invoices', { method: 'POST', body: JSON.stringify(payload) }),
  recognizeInvoice: (file: File, ipAssetId?: string) => {
    const form = new FormData()
    form.append('file', file)
    if (ipAssetId) form.append('ip_asset_id', ipAssetId)
    return request<{
      material_id: string
      status: 'pending' | 'running' | 'succeeded' | 'failed'
      fields: Record<string, string>
      warnings: string[]
    }>('/invoices/recognize', { method: 'POST', body: form })
  },
  async downloadMaterialFile(id: string, filename: string): Promise<void> {
    const token = getToken()
    const response = await fetch(`/api/materials/${id}/download`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!response.ok) throw new ApiError(response.status, `下载失败（${response.status}）`)
    const url = URL.createObjectURL(await response.blob())
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(url)
  },

  parties: (params: Record<string, unknown>) => request<Page<Record<string, unknown>>>(`/parties${toQuery(params)}`),
  persons: (params: Record<string, unknown>) => request<Page<Record<string, unknown>>>(`/persons${toQuery(params)}`),
  createPerson: (payload: unknown) =>
    request<Record<string, unknown>>('/persons', { method: 'POST', body: JSON.stringify(payload) }),
  agencies: (params: Record<string, unknown>) => request<Page<Record<string, unknown>>>(`/agencies${toQuery(params)}`),
  projects: (params: Record<string, unknown>) => request<Page<Record<string, unknown>>>(`/projects${toQuery(params)}`),

  users: (params: Record<string, unknown>) => request<Page<Record<string, unknown>>>(`/users${toQuery(params)}`),
  createUser: (payload: unknown) =>
    request<Record<string, unknown>>('/users', { method: 'POST', body: JSON.stringify(payload) }),
  updateUser: (id: string, payload: unknown) =>
    request<Record<string, unknown>>(`/users/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteUser: (id: string) => request<void>(`/users/${id}`, { method: 'DELETE' }),
  auditLogs: (params: Record<string, unknown>) =>
    request<Page<Record<string, unknown>>>(`/audit-logs${toQuery(params)}`),
  downloadImportTemplate: () => downloadAuthorized('/import/assets/template.xlsx', '知识产权导入模板.xlsx'),
  importAssets: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<{ total_rows: number; created: number; skipped: number; errors: Array<{ row: number; message: string }> }>(
      '/import/assets',
      { method: 'POST', body: form },
    )
  },
  exportAssetsCsv: (params: Record<string, unknown> = {}) =>
    downloadAuthorized(`/export/assets.csv${toQuery(params)}`, '知识产权档案.csv'),
  exportAssetsXlsx: (params: Record<string, unknown> = {}) =>
    downloadAuthorized(`/export/assets.xlsx${toQuery(params)}`, '知识产权档案.xlsx'),
}

export function exportAssetsUrl(params: Record<string, unknown> = {}): string {
  return `/api/export/assets.csv${toQuery(params)}`
}

export function exportAssetsXlsxUrl(params: Record<string, unknown> = {}): string {
  return `/api/export/assets.xlsx${toQuery(params)}`
}

export { statusLabels, typeLabels } from './labels'

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  return value.slice(0, 10)
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const iso = value.trim()
  // 后端数据库以 UTC 存储；无时区后缀时按 UTC 解析。
  const hasOffset = /(Z|[+-]\d{2}:?\d{2})$/.test(iso)
  const date = new Date(hasOffset ? iso : `${iso}Z`)
  if (Number.isNaN(date.getTime())) return iso.slice(0, 19).replace('T', ' ')
  // 转北京时间（UTC+8，无夏令时）。
  const beijing = new Date(date.getTime() + 8 * 60 * 60 * 1000)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${beijing.getUTCFullYear()}-${pad(beijing.getUTCMonth() + 1)}-${pad(beijing.getUTCDate())} ${pad(beijing.getUTCHours())}:${pad(beijing.getUTCMinutes())}:${pad(beijing.getUTCSeconds())}`
}
