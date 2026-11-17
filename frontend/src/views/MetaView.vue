<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { api } from '../api'
import { partyTypeLabels } from '../labels'
import { useAuth } from '../auth'
import { useToast } from '../toast'

type Row = Record<string, unknown>
type Tab = '权利人' | '代理机构' | '项目 / 产品'
type FormMode = 'create' | 'edit'

const allTabs: Tab[] = ['权利人', '代理机构', '项目 / 产品']
const { canWrite } = useAuth()
const toast = useToast()
const tabs = allTabs
const active = ref<Tab>('权利人')
const rows = ref<Row[]>([])
const loading = ref(true)
const error = ref('')
const keyword = ref('')
const pageSize = 20
const pageByTab = reactive<Record<Tab, number>>({
  权利人: 1,
  代理机构: 1,
  '项目 / 产品': 1,
})
const totalByTab = reactive<Record<Tab, number>>({
  权利人: 0,
  代理机构: 0,
  '项目 / 产品': 0,
})

interface Column {
  key: string
  label: string
  render?: (row: Row) => string
}

const baseColumns: Record<Tab, Column[]> = {
  权利人: [
    { key: 'name', label: '名称' },
    { key: 'party_type', label: '类型', render: (row) => partyTypeLabels[String(row.party_type)] ?? String(row.party_type ?? '—') },
    { key: 'country', label: '国家 / 地区' },
    { key: 'contact', label: '联系人' },
    { key: 'phone', label: '电话' },
  ],
  代理机构: [
    { key: 'name', label: '机构名称' },
    { key: 'service_type', label: '服务类型' },
    { key: 'contact', label: '联系人' },
    { key: 'phone', label: '电话' },
    { key: 'email', label: '邮箱' },
  ],
  '项目 / 产品': [
    { key: 'name', label: '名称' },
    { key: 'code', label: '编号' },
    { key: 'owner_display_name', label: '负责人' },
    { key: 'start_date', label: '开始日期' },
    { key: 'status', label: '状态' },
  ],
}

const canManageActive = computed(() => canWrite.value)
const columns = computed(() => {
  const list = baseColumns[active.value].slice()
  if (canManageActive.value) list.push({ key: 'actions', label: '操作' })
  return list
})
const searchPlaceholder = computed(() => {
  if (active.value === '项目 / 产品') return '搜索项目 / 产品名称或编号'
  if (active.value === '代理机构') return '搜索机构名称或联系人'
  return '搜索权利人名称'
})
const createLabel = computed(() => `＋ 新建${active.value}`)
const drawerTitle = computed(() => `${formMode.value === 'create' ? '新建' : '编辑'}${active.value}`)

const showDrawer = ref(false)
const drawerEl = ref<HTMLElement | null>(null)
const formMode = ref<FormMode>('create')
const editingId = ref('')
const saving = ref(false)
const formError = ref('')
const form = reactive<Record<string, any>>({})

const deleteTarget = ref<{ id: string; name: string; tab: Tab } | null>(null)
const deleting = ref(false)

let searchTimer: ReturnType<typeof setTimeout> | undefined
let loadSeq = 0

function display(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? '是' : '否'
  return String(value)
}

async function load() {
  const seq = ++loadSeq
  const current = active.value
  loading.value = true
  error.value = ''

  try {
    const params: Record<string, unknown> = {
      page: pageByTab[current],
      page_size: pageSize,
    }
    if (keyword.value.trim()) params.q = keyword.value.trim()

    let result: { items: Row[]; total: number }
    if (current === '权利人') result = await api.parties(params)
    else if (current === '代理机构') result = await api.agencies(params)
    else result = await api.projects(params)

    if (seq !== loadSeq) return
    rows.value = result.items
    totalByTab[current] = result.total
  } catch (err) {
    if (seq !== loadSeq) return
    rows.value = []
    totalByTab[current] = 0
    error.value = err instanceof Error ? err.message : '加载失败'
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

function switchTab(tab: Tab) {
  if (tab === active.value) return
  active.value = tab
  pageByTab[tab] = 1
  keyword.value = ''
  showDrawer.value = false
  void load()
}

function onSearch() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    pageByTab[active.value] = 1
    void load()
  }, 300)
}

function changePage(delta: number) {
  const next = pageByTab[active.value] + delta
  if (next < 1 || (next - 1) * pageSize >= totalByTab[active.value]) return
  pageByTab[active.value] = next
  void load()
}

function defaultsFor(tab: Tab): Record<string, any> {
  if (tab === '权利人') {
    return {
      name: '',
      party_type: 'company',
      id_number: '',
      country: '',
      address: '',
      contact: '',
      phone: '',
      email: '',
      is_default: false,
    }
  }
  if (tab === '代理机构') {
    return {
      name: '',
      contact: '',
      phone: '',
      email: '',
      address: '',
      service_type: '',
      remark: '',
    }
  }
  return {
    name: '',
    code: '',
    owner_user_id: '',
    start_date: '',
    status: '',
    remark: '',
  }
}

function resetForm(values: Record<string, any>) {
  Object.keys(form).forEach((key) => delete form[key])
  Object.assign(form, values)
}

function openCreate() {
  formMode.value = 'create'
  editingId.value = ''
  formError.value = ''
  resetForm(defaultsFor(active.value))
  showDrawer.value = true
}

function openEdit(row: Row) {
  formMode.value = 'edit'
  editingId.value = String(row.id ?? '')
  formError.value = ''
  const values = defaultsFor(active.value)
  for (const key of Object.keys(values)) {
    if (row[key] !== undefined && row[key] !== null) values[key] = row[key]
  }
  if (active.value === '项目 / 产品') {
    values.start_date = row.start_date ? String(row.start_date).slice(0, 10) : ''
    values.owner_user_id = row.owner_user_id ?? ''
  }
  resetForm(values)
  showDrawer.value = true
}

function closeDrawer() {
  if (saving.value) return
  showDrawer.value = false
}

function nullable(value: unknown): string | null {
  const text = typeof value === 'string' ? value.trim() : ''
  return text || null
}

async function save() {
  formError.value = ''
  const tab = active.value

  if (tab === '权利人') {
    if (!String(form.name ?? '').trim()) {
      formError.value = '名称必填'
      return
    }
    const payload = {
      name: String(form.name).trim(),
      party_type: form.party_type,
      id_number: nullable(form.id_number),
      country: nullable(form.country),
      address: nullable(form.address),
      contact: nullable(form.contact),
      phone: nullable(form.phone),
      email: nullable(form.email),
      is_default: Boolean(form.is_default),
    }
    saving.value = true
    try {
      if (formMode.value === 'create') await api.createParty(payload)
      else await api.updateParty(editingId.value, payload)
      showDrawer.value = false
      toast.success(formMode.value === 'create' ? '权利人已新建' : '权利人已更新')
      await load()
    } catch (err) {
      formError.value = err instanceof Error ? err.message : '保存失败'
    } finally {
      saving.value = false
    }
    return
  }

  if (tab === '代理机构') {
    if (!String(form.name ?? '').trim()) {
      formError.value = '机构名称必填'
      return
    }
    const payload = {
      name: String(form.name).trim(),
      contact: nullable(form.contact),
      phone: nullable(form.phone),
      email: nullable(form.email),
      address: nullable(form.address),
      service_type: nullable(form.service_type),
      remark: nullable(form.remark),
    }
    saving.value = true
    try {
      if (formMode.value === 'create') await api.createAgency(payload)
      else await api.updateAgency(editingId.value, payload)
      showDrawer.value = false
      toast.success(formMode.value === 'create' ? '代理机构已新建' : '代理机构已更新')
      await load()
    } catch (err) {
      formError.value = err instanceof Error ? err.message : '保存失败'
    } finally {
      saving.value = false
    }
    return
  }

  if (!String(form.name ?? '').trim()) {
    formError.value = '名称必填'
    return
  }
  const payload = {
    name: String(form.name).trim(),
    code: nullable(form.code),
    owner_user_id: form.owner_user_id || null,
    start_date: nullable(form.start_date),
    status: nullable(form.status),
    remark: nullable(form.remark),
  }
  saving.value = true
  try {
    if (formMode.value === 'create') await api.createProject(payload)
    else await api.updateProject(editingId.value, payload)
    showDrawer.value = false
    toast.success(formMode.value === 'create' ? '项目 / 产品已新建' : '项目 / 产品已更新')
    await load()
  } catch (err) {
    formError.value = err instanceof Error ? err.message : '保存失败'
  } finally {
    saving.value = false
  }
}

function openDelete(row: Row) {
  if (!canManageActive.value) return
  deleteTarget.value = {
    id: String(row.id),
    name: String(row.display_name ?? row.name ?? '该记录'),
    tab: active.value,
  }
}

function closeDelete() {
  if (deleting.value) return
  deleteTarget.value = null
}

const deleteDescription = computed(() => {
  if (!deleteTarget.value) return ''
  if (deleteTarget.value.tab === '权利人') {
    return '删除后不再出现在权利人选择列表中；已关联档案保留历史记录。'
  }
  if (deleteTarget.value.tab === '代理机构') {
    return '删除后不再出现在代理机构选择列表中；已关联档案保留历史记录。'
  }
  return '删除后不再出现在项目 / 产品选择列表中；已关联档案不会被删除。'
})

async function confirmDelete() {
  if (!deleteTarget.value) return
  deleting.value = true
  try {
    const target = deleteTarget.value
    if (target.tab === '权利人') await api.deleteParty(target.id)
    else if (target.tab === '代理机构') await api.deleteAgency(target.id)
    else await api.deleteProject(target.id)
    deleteTarget.value = null
    toast.success('已删除')
    await load()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '删除失败'
    deleteTarget.value = null
  } finally {
    deleting.value = false
  }
}

onMounted(() => {
  void load()
})

onBeforeUnmount(() => {
  if (searchTimer) clearTimeout(searchTimer)
})
</script>

<template>
  <section>
    <div class="page-head">
      <div>
        <h1>基础资料</h1>
        <p>维护权利人、代理机构与项目 / 产品；人员即系统用户，统一在系统管理 → 用户中维护。</p>
      </div>
    </div>

    <div class="tabs">
      <button
        v-for="tab in tabs"
        :key="tab"
        class="tab"
        :class="{ active: active === tab }"
        @click="switchTab(tab)"
      >
        {{ tab }}
      </button>
    </div>

    <div class="toolbar">
      <button v-if="canManageActive" class="button primary" @click="openCreate">{{ createLabel }}</button>
      <input v-model="keyword" class="field" style="min-width: 280px" :placeholder="searchPlaceholder" @input="onSearch" />
      <span class="hint">共 {{ totalByTab[active] }} 条</span>
    </div>

    <p v-if="error" class="error-text">{{ error }}</p>

    <div class="panel table-panel">
      <table class="data">
        <thead>
          <tr>
            <th v-for="column in columns" :key="column.key">{{ column.label }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td :colspan="columns.length" class="empty">加载中…</td>
          </tr>
          <tr v-else-if="rows.length === 0">
            <td :colspan="columns.length" class="empty">暂无数据</td>
          </tr>
          <template v-else>
            <tr v-for="(row, index) in rows" :key="String(row.id ?? index)">
              <td v-for="column in columns" :key="column.key">
                <template v-if="column.key === 'actions'">
                  <button class="button small" @click="openEdit(row)">编辑</button>
                  <button class="button small danger" @click="openDelete(row)">删除</button>
                </template>
                <template v-else-if="column.key === 'is_active'">
                  <span class="badge" :class="row.is_active ? 'green' : 'gray'">{{ row.is_active ? '启用' : '停用' }}</span>
                </template>
                <template v-else>{{ column.render ? column.render(row) : display(row[column.key]) }}</template>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
      <div class="pagination">
        <span>共 {{ totalByTab[active] }} 条</span>
        <span>
          <button class="button small" :disabled="pageByTab[active] <= 1 || loading" @click="changePage(-1)">上一页</button>
          <span style="margin: 0 8px">第 {{ pageByTab[active] }} 页</span>
          <button
            class="button small"
            :disabled="pageByTab[active] * pageSize >= totalByTab[active] || loading"
            @click="changePage(1)"
          >下一页</button>
        </span>
      </div>
    </div>

    <div v-if="showDrawer">
      <div class="drawer-backdrop" @click="closeDrawer"></div>
      <aside ref="drawerEl" class="drawer" role="dialog" aria-modal="true" :aria-label="drawerTitle">
        <header>
          <small>基础资料 · {{ active }}</small>
          <h2>{{ drawerTitle }}</h2>
        </header>
        <div class="drawer-body">
          <div v-if="active === '权利人'" class="form-grid">
            <div class="form-item full">
              <label for="p_name">名称 *</label>
              <input id="p_name" v-model="form.name" placeholder="请输入权利人名称" />
            </div>
            <div class="form-item">
              <label for="p_type">权利人类型</label>
              <select id="p_type" v-model="form.party_type">
                <option value="company">企业</option>
                <option value="person">个人</option>
                <option value="organization">其他组织</option>
              </select>
            </div>
            <div class="form-item">
              <label for="p_id_number">证件号 / 统一社会信用代码</label>
              <input id="p_id_number" v-model="form.id_number" placeholder="可选" />
            </div>
            <div class="form-item">
              <label for="p_country">国家 / 地区</label>
              <input id="p_country" v-model="form.country" placeholder="可选" />
            </div>
            <div class="form-item">
              <label for="p_contact">联系人</label>
              <input id="p_contact" v-model="form.contact" placeholder="可选" />
            </div>
            <div class="form-item">
              <label for="p_phone">电话</label>
              <input id="p_phone" v-model="form.phone" placeholder="可选" />
            </div>
            <div class="form-item">
              <label for="p_email">邮箱</label>
              <input id="p_email" v-model="form.email" placeholder="可选" />
            </div>
            <div class="form-item full">
              <label for="p_address">地址</label>
              <input id="p_address" v-model="form.address" placeholder="可选" />
            </div>
            <div class="form-item full">
              <label class="check-line"><input v-model="form.is_default" type="checkbox" /> 设为默认权利人</label>
            </div>
          </div>

          <div v-else-if="active === '代理机构'" class="form-grid">
            <div class="form-item full">
              <label for="a_name">机构名称 *</label>
              <input id="a_name" v-model="form.name" placeholder="请输入代理机构名称" />
            </div>
            <div class="form-item">
              <label for="a_service">服务类型</label>
              <input id="a_service" v-model="form.service_type" placeholder="例如：专利代理" />
            </div>
            <div class="form-item">
              <label for="a_contact">联系人</label>
              <input id="a_contact" v-model="form.contact" placeholder="可选" />
            </div>
            <div class="form-item">
              <label for="a_phone">电话</label>
              <input id="a_phone" v-model="form.phone" placeholder="可选" />
            </div>
            <div class="form-item">
              <label for="a_email">邮箱</label>
              <input id="a_email" v-model="form.email" placeholder="可选" />
            </div>
            <div class="form-item full">
              <label for="a_address">地址</label>
              <input id="a_address" v-model="form.address" placeholder="可选" />
            </div>
            <div class="form-item full">
              <label for="a_remark">备注</label>
              <textarea id="a_remark" v-model="form.remark" placeholder="可选"></textarea>
            </div>
          </div>

          <div v-else class="form-grid">
            <div class="form-item full">
              <label for="pr_name">项目 / 产品名称 *</label>
              <input id="pr_name" v-model="form.name" placeholder="请输入名称" />
            </div>
            <div class="form-item">
              <label for="pr_code">编号</label>
              <input id="pr_code" v-model="form.code" placeholder="可选" />
            </div>
            <div class="form-item">
              <label for="pr_start">开始日期</label>
              <input id="pr_start" v-model="form.start_date" type="date" />
            </div>
            <div class="form-item">
              <label for="pr_status">状态</label>
              <input id="pr_status" v-model="form.status" placeholder="例如：进行中" />
            </div>
            <div class="form-item full">
              <label for="pr_remark">备注</label>
              <textarea id="pr_remark" v-model="form.remark" placeholder="可选"></textarea>
            </div>
          </div>

          <p v-if="formError" class="error-text" style="margin-top: 12px">{{ formError }}</p>
        </div>
        <footer>
          <button class="button ghost" :disabled="saving" @click="closeDrawer">取消</button>
          <button class="button primary" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存' }}</button>
        </footer>
      </aside>
    </div>

    <div v-if="deleteTarget" class="confirm-backdrop" @click="closeDelete">
      <section class="confirm-modal" role="dialog" aria-modal="true" aria-labelledby="delete_title" @click.stop>
        <header>
          <small>删除确认</small>
          <h2 id="delete_title">删除{{ deleteTarget.tab }}？</h2>
        </header>
        <div class="confirm-body">
          <p>确定删除「<strong>{{ deleteTarget.name }}</strong>」吗？</p>
          <p class="hint">{{ deleteDescription }}</p>
          <p class="hint">删除为逻辑删除，历史关联与审计记录保留。</p>
        </div>
        <footer>
          <button class="button ghost" :disabled="deleting" @click="closeDelete">取消</button>
          <button class="button danger" :disabled="deleting" @click="confirmDelete">{{ deleting ? '删除中…' : '确认删除' }}</button>
        </footer>
      </section>
    </div>
  </section>
</template>

<style scoped>
.flash-line {
  margin: 0 0 12px;
  padding: 8px 12px;
  border-radius: 8px;
  background: #e8f7f1;
  color: #16865a;
  font-size: 12px;
}
.button.danger {
  color: var(--red);
  border-color: #f3c7cc;
}
.button.danger:hover {
  color: #b83d49;
  border-color: #e9a7ae;
  background: #fff7f8;
}
.data td .button + .button {
  margin-left: 6px;
}
.check-line {
  display: flex;
  align-items: center;
  gap: 8px;
}
.confirm-backdrop {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: grid;
  place-items: center;
  background: rgba(7, 18, 38, 0.42);
}
.confirm-modal {
  width: 440px;
  max-width: calc(100% - 32px);
  background: #fff;
  border-radius: 14px;
  box-shadow: 0 30px 80px rgba(7, 18, 38, 0.25);
  overflow: hidden;
}
.confirm-modal header,
.confirm-modal footer {
  padding: 18px 22px;
}
.confirm-modal header {
  border-bottom: 1px solid var(--line);
}
.confirm-modal header small {
  font-size: 11px;
  color: var(--blue);
}
.confirm-modal h2 {
  margin: 4px 0 0;
  font-size: 17px;
}
.confirm-body {
  padding: 20px 22px;
}
.confirm-body p {
  margin: 0 0 10px;
  font-size: 13px;
}
.confirm-body p:last-child {
  margin-bottom: 0;
}
.confirm-modal footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  border-top: 1px solid var(--line);
}
</style>
