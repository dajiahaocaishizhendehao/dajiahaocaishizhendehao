<script setup lang="ts">
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { api, formatDate, formatDateTime } from '../api'
import { roleLabels } from '../labels'
import { useAuth } from '../auth'
import { useToast } from '../toast'

interface UserRow {
  id: string
  username: string
  display_name: string
  role: string
  email: string | null
  phone: string | null
  is_active: boolean
}

interface AuditRow {
  id: string
  action: string
  object_type: string
  summary: string | null
  ip_address: string | null
  created_at: string
}

const { canAdmin, currentUser } = useAuth()
const toast = useToast()
const tab = ref<'users' | 'logs'>('users')
const users = ref<UserRow[]>([])
const logs = ref<AuditRow[]>([])
const loading = ref(true)
const error = ref('')
const keyword = ref('')
const pageSize = 20
const userPage = ref(1)
const userTotal = ref(0)
const logPage = ref(1)
const logTotal = ref(0)

const showDrawer = ref(false)
const formMode = ref<'create' | 'edit'>('create')
const editingId = ref('')
const saving = ref(false)
const formError = ref('')

const deleteTarget = ref<{ id: string; name: string } | null>(null)
const deleting = ref(false)

const actionLabels: Record<string, string> = {
  create: '新增',
  update: '修改',
  delete: '删除',
  export: '导出',
  import: '导入',
  download_template: '下载模板',
  login: '登录',
  logout: '退出',
  complete: '标记完成',
  upload: '上传',
  extract: '材料识别',
  download: '下载',
  recognize_invoice: '识别发票',
  link_invoice: '关联发票',
}

const objectTypeLabels: Record<string, string> = {
  ip_asset: '知识产权档案',
  user: '用户',
  certificate: '证书',
  date_item: '日期事项',
  fee: '费用',
  invoice: '发票',
  material: '材料',
  party: '权利人',
  agency: '代理机构',
  project: '项目 / 产品',
  person: '人员',
}

const form = reactive({
  username: '',
  display_name: '',
  password: '',
  role: 'user',
  email: '',
  phone: '',
  is_active: true,
})

const editingSelf = ref(false)
const drawerTitle = ref('新建用户')

let searchTimer: ReturnType<typeof setTimeout> | undefined

function nullable(value: string): string | null {
  const text = value.trim()
  return text || null
}

async function loadUsers() {
  loading.value = true
  error.value = ''
  try {
    const params: Record<string, unknown> = { page: userPage.value, page_size: pageSize }
    if (keyword.value.trim()) params.q = keyword.value.trim()
    const result = await api.users(params)
    users.value = result.items as unknown as UserRow[]
    userTotal.value = result.total
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败'
  } finally {
    loading.value = false
  }
}

async function loadLogs() {
  loading.value = true
  error.value = ''
  try {
    const result = await api.auditLogs({ page: logPage.value, page_size: pageSize })
    logs.value = result.items as unknown as AuditRow[]
    logTotal.value = result.total
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败'
  } finally {
    loading.value = false
  }
}

function switchTab(next: 'users' | 'logs') {
  if (tab.value === next) return
  tab.value = next
  error.value = ''
  if (next === 'users') {
    userPage.value = 1
    void loadUsers()
  } else {
    logPage.value = 1
    void loadLogs()
  }
}

function onSearch() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    userPage.value = 1
    void loadUsers()
  }, 300)
}

function changePage(delta: number) {
  const next = userPage.value + delta
  if (next < 1 || (next - 1) * pageSize >= userTotal.value) return
  userPage.value = next
  void loadUsers()
}

function resetForm() {
  form.username = ''
  form.display_name = ''
  form.password = ''
  form.role = 'user'
  form.email = ''
  form.phone = ''
  form.is_active = true
}

function openCreate() {
  formMode.value = 'create'
  editingId.value = ''
  editingSelf.value = false
  drawerTitle.value = '新建用户'
  formError.value = ''
  resetForm()
  showDrawer.value = true
}

function openEdit(row: UserRow) {
  formMode.value = 'edit'
  editingId.value = row.id
  editingSelf.value = row.id === currentUser.value?.id
  drawerTitle.value = '编辑用户'
  formError.value = ''
  form.username = row.username
  form.display_name = row.display_name
  form.password = ''
  form.role = row.role
  form.email = row.email ?? ''
  form.phone = row.phone ?? ''
  form.is_active = row.is_active
  showDrawer.value = true
}

function closeDrawer() {
  if (saving.value) return
  showDrawer.value = false
}

async function save() {
  formError.value = ''
  if (formMode.value === 'create' && form.username.trim().length < 3) {
    formError.value = '账号至少 3 位'
    return
  }
  if (!form.display_name.trim()) {
    formError.value = '姓名必填'
    return
  }
  if (formMode.value === 'create' && form.password.length < 8) {
    formError.value = '初始密码至少 8 位'
    return
  }
  if (formMode.value === 'edit' && form.password && form.password.length < 8) {
    formError.value = '新密码至少 8 位，或留空不修改'
    return
  }
  if (editingSelf.value && form.role !== 'admin') {
    formError.value = '不能修改当前登录账号的角色'
    return
  }
  if (editingSelf.value && !form.is_active) {
    formError.value = '不能停用当前登录账号'
    return
  }

  saving.value = true
  try {
    if (formMode.value === 'create') {
      await api.createUser({
        username: form.username.trim(),
        display_name: form.display_name.trim(),
        password: form.password,
        role: form.role,
        email: nullable(form.email),
        phone: nullable(form.phone),
      })
      toast.success('用户已新建')
    } else {
      const payload: Record<string, unknown> = {
        display_name: form.display_name.trim(),
        role: form.role,
        email: nullable(form.email),
        phone: nullable(form.phone),
        is_active: form.is_active,
      }
      if (form.password) payload.password = form.password
      await api.updateUser(editingId.value, payload)
      toast.success('用户已更新')
    }
    showDrawer.value = false
    await loadUsers()
  } catch (err) {
    formError.value = err instanceof Error ? err.message : '保存失败'
  } finally {
    saving.value = false
  }
}

function openDelete(row: UserRow) {
  if (!canAdmin.value) return
  if (row.id === currentUser.value?.id) return
  deleteTarget.value = { id: row.id, name: row.display_name || row.username }
}

function closeDelete() {
  if (deleting.value) return
  deleteTarget.value = null
}

async function confirmDelete() {
  if (!deleteTarget.value) return
  deleting.value = true
  try {
    await api.deleteUser(deleteTarget.value.id)
    deleteTarget.value = null
    toast.success('已删除')
    await loadUsers()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '删除失败'
    deleteTarget.value = null
  } finally {
    deleting.value = false
  }
}

onMounted(() => {
  void loadUsers()
})

onBeforeUnmount(() => {
  if (searchTimer) clearTimeout(searchTimer)
})
</script>

<template>
  <section>
    <div class="page-head">
      <div>
        <h1>系统管理</h1>
        <p>用户与角色、操作审计；人员即系统用户，统一在此维护。</p>
      </div>
    </div>

    <div class="tabs">
      <button class="tab" :class="{ active: tab === 'users' }" @click="switchTab('users')">用户</button>
      <button class="tab" :class="{ active: tab === 'logs' }" @click="switchTab('logs')">操作日志</button>
    </div>

    <div v-if="tab === 'users'" class="toolbar">
      <button v-if="canAdmin" class="button primary" @click="openCreate">＋ 新建用户</button>
      <input
        v-model="keyword"
        class="field"
        style="min-width: 280px"
        placeholder="搜索姓名或登录账号"
        @input="onSearch"
      />
      <span class="hint">共 {{ userTotal }} 条</span>
    </div>

    <p v-if="error" class="error-text">{{ error }}</p>

    <div v-if="tab === 'users'" class="panel table-panel">
      <table class="data">
        <thead>
          <tr>
            <th>账号</th>
            <th>姓名</th>
            <th>角色</th>
            <th>手机</th>
            <th>邮箱</th>
            <th>状态</th>
            <th v-if="canAdmin">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in users" :key="item.id">
            <td>{{ item.username }}</td>
            <td>{{ item.display_name }}</td>
            <td>{{ roleLabels[item.role] ?? item.role }}</td>
            <td>{{ item.phone || '—' }}</td>
            <td>{{ item.email || '—' }}</td>
            <td><span class="badge" :class="item.is_active ? 'green' : 'gray'">{{ item.is_active ? '启用' : '停用' }}</span></td>
            <td v-if="canAdmin">
              <button class="button small" @click="openEdit(item)">编辑</button>
              <button
                class="button small danger"
                :disabled="item.id === currentUser?.id"
                :title="item.id === currentUser?.id ? '不能删除当前登录账号' : ''"
                @click="openDelete(item)"
              >删除</button>
            </td>
          </tr>
          <tr v-if="loading"><td :colspan="canAdmin ? 7 : 6" class="empty">加载中…</td></tr>
          <tr v-else-if="users.length === 0"><td :colspan="canAdmin ? 7 : 6" class="empty">暂无用户</td></tr>
        </tbody>
      </table>
      <div class="pagination">
        <span>共 {{ userTotal }} 条</span>
        <span>
          <button class="button small" :disabled="userPage <= 1 || loading" @click="changePage(-1)">上一页</button>
          <span style="margin: 0 8px">第 {{ userPage }} 页</span>
          <button class="button small" :disabled="userPage * pageSize >= userTotal || loading" @click="changePage(1)">下一页</button>
        </span>
      </div>
    </div>

    <div v-else class="panel table-panel">
      <table class="data">
        <thead>
          <tr><th>时间</th><th>动作</th><th>对象</th><th>摘要</th><th>IP</th></tr>
        </thead>
        <tbody>
          <tr v-for="item in logs" :key="item.id">
            <td>{{ formatDateTime(item.created_at) }}</td>
            <td>{{ actionLabels[item.action] ?? item.action }}</td>
            <td>{{ objectTypeLabels[item.object_type] ?? item.object_type }}</td>
            <td>{{ item.summary || '—' }}</td>
            <td>{{ item.ip_address || '—' }}</td>
          </tr>
          <tr v-if="loading"><td colspan="5" class="empty">加载中…</td></tr>
          <tr v-else-if="logs.length === 0"><td colspan="5" class="empty">暂无日志</td></tr>
        </tbody>
      </table>
      <div class="pagination">
        <span>共 {{ logTotal }} 条</span>
        <span>
          <button class="button small" :disabled="logPage <= 1 || loading" @click="logPage--; loadLogs()">上一页</button>
          <span style="margin: 0 8px">第 {{ logPage }} 页</span>
          <button class="button small" :disabled="logPage * pageSize >= logTotal || loading" @click="logPage++; loadLogs()">下一页</button>
        </span>
      </div>
    </div>

    <div v-if="showDrawer">
      <div class="drawer-backdrop" @click="closeDrawer"></div>
      <aside class="drawer" role="dialog" aria-modal="true" :aria-label="drawerTitle">
        <header>
          <small>系统管理</small>
          <h2>{{ drawerTitle }}</h2>
        </header>
        <div class="drawer-body">
          <div class="form-grid">
            <div class="form-item">
              <label for="u_name">账号 *</label>
              <input id="u_name" v-model="form.username" :disabled="formMode === 'edit'" autocomplete="off" />
            </div>
            <div class="form-item">
              <label for="u_display">姓名 *</label>
              <input id="u_display" v-model="form.display_name" />
            </div>
            <div class="form-item">
              <label for="u_role">角色</label>
              <select id="u_role" v-model="form.role">
                <option value="admin">系统管理员</option>
                <option value="ip_admin">管理员</option>
                <option value="user">普通用户</option>
              </select>
            </div>
            <div class="form-item">
              <label for="u_phone">手机</label>
              <input id="u_phone" v-model="form.phone" placeholder="可选" />
            </div>
            <div class="form-item">
              <label for="u_email">邮箱</label>
              <input id="u_email" v-model="form.email" placeholder="可选" />
            </div>
            <div v-if="formMode === 'edit'" class="form-item">
              <label for="u_status">状态</label>
              <select id="u_status" v-model="form.is_active" :disabled="editingSelf">
                <option :value="true">启用</option>
                <option :value="false">停用</option>
              </select>
            </div>
            <div v-if="formMode === 'create'" class="form-item full">
              <label for="u_password">初始密码 *</label>
              <input id="u_password" v-model="form.password" type="password" autocomplete="new-password" placeholder="至少 8 位" />
            </div>
            <div v-else class="form-item full">
              <label for="u_password">重置密码</label>
              <input id="u_password" v-model="form.password" type="password" autocomplete="new-password" placeholder="留空则不修改，至少 8 位" />
            </div>
          </div>
          <p v-if="formError" class="error-text" style="margin-top: 12px">{{ formError }}</p>
          <p class="hint" style="margin-top: 12px">密码只在创建或重置时提交一次，数据库仅保存哈希，接口从不返回密码。</p>
        </div>
        <footer>
          <button class="button ghost" :disabled="saving" @click="closeDrawer">取消</button>
          <button class="button primary" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存' }}</button>
        </footer>
      </aside>
    </div>

    <div v-if="deleteTarget" class="confirm-backdrop" @click="closeDelete">
      <section class="confirm-modal" role="dialog" aria-modal="true" aria-labelledby="delete_user_title" @click.stop>
        <header>
          <small>删除确认</small>
          <h2 id="delete_user_title">删除用户？</h2>
        </header>
        <div class="confirm-body">
          <p>确定删除「<strong>{{ deleteTarget.name }}</strong>」吗？</p>
          <p class="hint">删除后该用户将无法登录系统，历史操作与审计记录保留。</p>
          <p class="hint">删除为逻辑删除，不会物理清除数据。</p>
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
